"""Omni Brain RAG answer API.

From your project root:
    python -m uvicorn backend.rag_api:app --reload --port 8000

Open http://127.0.0.1:8000/docs and POST to /ask.

Requires the existing backend/semantic_search.py and an already embedded
PostgreSQL document_chunks table. The retrieved Related sections are displayed
as supplemental references, but they are NOT given to the model as evidence.
"""

import logging
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from backend.ai_client import make_client, model_name
from backend.live_data import LiveDataError, TICKET_PRIORITIES, answer_live_question, clients_with_overdue_tasks
from backend.semantic_search import search_documents

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

logger = logging.getLogger("omni_brain_rag")
MODEL = model_name(os.getenv("RAG_MODEL", "gpt-5.4-mini"))
MAX_CHUNK_CHARS = 3500
MAX_TOTAL_CONTEXT_CHARS = 16000

INSTRUCTIONS = """
You are an IT support assistant answering questions
using retrieved company documentation.

RULES:
1. You may receive up to 5 primary document chunks.
   These are candidate sources, not mandatory sources.

2. Evaluate each chunk independently for relevance
   to the user's question.

3. Use ONLY the chunks that directly support your answer.
   You may use 1, 2, 3, or any number of relevant chunks.

4. Do not include information simply because it appears
   in a retrieved chunk.

5. Do not attempt to reference every retrieved source.

6. Cite only sources you actually use to support claims.
   Use citation identifiers such as [1] or [2].

7. If none of the chunks adequately answer the question,
   state that the available documentation is insufficient.

8. Never invent facts to fill gaps in the documentation.

9. Treat Related Documents chunks as supplementary
   references, not primary evidence.
10. When the answer describes two or more actions in sequence, put each action
    in the steps array in order, even if the source describes them in prose.
    Keep each step short and cite its supporting source where appropriate.
    Do not include numbers in the step strings; the interface numbers them.
    Do not put those actions in one paragraph in answer.
11. When steps is nonempty, answer is a brief introduction and closing_note
    holds any conditions, exceptions, or follow-up. Do not repeat the steps in
    either field. Otherwise, put the complete natural-language response in
    answer, leave steps empty, and leave closing_note empty. Never put JSON in
    the answer.
12. For onboarding or another repeatable workflow with concrete steps in the
    primary sources, set suggest_process_plan to true and provide a draft,
    even when the user asks "how do I..." rather than requesting a plan by name.
    A missing client name is okay: leave company_name empty for the user to fill.
    For ordinary questions or insufficiently supported workflows, set
    suggest_process_plan to false and leave the plan empty.
13. A suggested plan must have a name and 1-5 milestones with actionable tasks.
    Use only steps supported by the primary sources; do not invent work.
14. When the user names a company, copy that name into company_name exactly,
    including a suffix such as Corp. or Inc. The name can come from the user's
    question even when it is absent from the documents. Leave company_name
    empty only when the user did not name one. Never invent a deadline or assignee.
15. The plan is a draft for the user to review, never an instruction to create
    or modify anything automatically. Do not ask whether the user wants a
    checklist when you can provide a supported process plan draft."""

REPLY_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "omni_assistant_reply",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "answer": {"type": "string"},
                "steps": {"type": "array", "items": {"type": "string"}},
                "closing_note": {"type": "string"},
                "suggest_process_plan": {"type": "boolean"},
                "process_plan": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "company_name": {"type": "string"},
                        "milestones": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "tasks": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {"title": {"type": "string"}},
                                            "required": ["title"],
                                            "additionalProperties": False,
                                        },
                                    },
                                },
                                "required": ["title", "tasks"],
                                "additionalProperties": False,
                            },
                        },
                    },
                    "required": ["name", "company_name", "milestones"],
                    "additionalProperties": False,
                },
            },
            "required": ["answer", "steps", "closing_note", "suggest_process_plan", "process_plan"],
            "additionalProperties": False,
        },
    }
}


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)
    primary_limit: int = Field(default=5, ge=1, le=10)
    related_limit: int = Field(default=2, ge=0, le=5)


class Source(BaseModel):
    citation: str
    chunk_id: int
    document_title: str
    source_path: str | None
    chunk_index: int
    similarity: float


class RelatedReference(BaseModel):
    chunk_id: int
    document_title: str
    source_path: str | None
    chunk_index: int
    similarity: float


class SuggestedTask(BaseModel):
    title: str


class SuggestedMilestone(BaseModel):
    title: str
    tasks: list[SuggestedTask]


class SuggestedProcessPlan(BaseModel):
    name: str
    company_name: str
    milestones: list[SuggestedMilestone]


class ModelReply(BaseModel):
    answer: str
    steps: list[str]
    closing_note: str
    suggest_process_plan: bool
    process_plan: SuggestedProcessPlan


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[Source]
    related_references: list[RelatedReference]
    status: str
    model: str | None = None
    process_plan: SuggestedProcessPlan | None = None


def documented_onboarding(question: str, sources: list[Source]) -> bool:
    if not re.search(r"\bonboard(?:ing)?\b", question, flags=re.IGNORECASE):
        return False
    client_workflow = re.search(r"\b(client|company|customer)\b", question, flags=re.IGNORECASE)
    title_hint = "client onboarding" if client_workflow else "onboard"
    return any(title_hint in source.document_title.casefold() for source in sources)


def company_in_question(question: str) -> str:
    word = r"[A-Z][\w&'’.-]*"
    suffix = r"(?:Corporation|Corp\.?|Incorporated|Inc\.?|LLC|Limited|Ltd\.?|Company|Co\.?)"
    named = re.search(
        rf"\b(?P<name>(?:{word}\s+){{1,6}}{suffix})(?=$|[\s?!,;:])",
        question,
    )
    if named:
        return named.group("name")

    # A company without a legal suffix can still be named after "onboard" or "for".
    if not re.search(r"\b(?:onboard|oboard)(?:ing)?\b", question, re.IGNORECASE):
        return ""
    context = r"(?:(?i:onboard|oboard)(?:ing)?\s+(?:(?:a|an|the|client|company|customer|named)\s+)*|(?i:for)\s+)"
    named = re.search(
        rf"\b{context}(?P<name>{word}(?:\s+{word}){{0,5}})(?=$|[?!.;,]|\s+(?:in|on|with|using|through)\b)",
        question,
    )
    if named and named.group("name").casefold() not in {
        "new user", "user", "new client", "client", "new customer", "customer", "company"
    }:
        return named.group("name")
    return ""


def usable_plan(
    reply: ModelReply, question: str, answer: str, sources: list[Source], onboarding: bool = False
) -> SuggestedProcessPlan | None:
    if not reply.suggest_process_plan or (not onboarding and not any(source.citation in answer for source in sources)):
        return None
    name = reply.process_plan.name.strip()[:200]
    company_name = company_in_question(question) or reply.process_plan.company_name.strip()
    if company_name and company_name.casefold() not in question.casefold():
        company_name = ""
    company_name = company_name[:200]
    if company_name and re.search(r"\bonboard", name, re.IGNORECASE) and company_name.casefold() not in name.casefold():
        name = f"{company_name} onboarding"[:200]
    milestones = []
    for item in reply.process_plan.milestones[:5]:
        title = item.title.strip()[:200]
        tasks = [SuggestedTask(title=task.title.strip()[:200]) for task in item.tasks[:8] if task.title.strip()]
        if title and tasks:
            milestones.append(SuggestedMilestone(title=title, tasks=tasks))
    if not name or not milestones:
        return None
    return SuggestedProcessPlan(name=name, company_name=company_name, milestones=milestones)


def build_context(primary_results: list[dict]) -> tuple[str, list[Source]]:
    """Build an evidence-bounded prompt and its machine-readable citations."""
    parts: list[str] = []
    sources: list[Source] = []
    total = 0

    for result in primary_results:
        text = (result.get("content") or "").strip()
        if not text or total >= MAX_TOTAL_CONTEXT_CHARS:
            continue
        # Cap input, not the source stored in PostgreSQL.
        text = text[: min(MAX_CHUNK_CHARS, MAX_TOTAL_CONTEXT_CHARS - total)]
        label = f"[{len(sources) + 1}]"
        parts.append(
            f"{label} TITLE: {result['document_title']}\n"
            f"SOURCE_PATH: {result.get('source_path') or 'unknown'}\n"
            f"CHUNK_INDEX: {result['chunk_index']}\n"
            f"EXCERPT:\n{text}"
        )
        sources.append(Source(
            citation=label,
            chunk_id=result["chunk_id"],
            document_title=result["document_title"],
            source_path=result.get("source_path"),
            chunk_index=result["chunk_index"],
            similarity=result["similarity"],
        ))
        total += len(text)

    return "\n\n---\n\n".join(parts), sources


def live_question_context(question: str) -> str:
    text = question.casefold()
    if re.search(r"\b(tickets?|issues?)\b", text):
        priority = next((value for value in TICKET_PRIORITIES if re.search(rf"\b{value}\b", text)), None)
        return f"{priority}-priority tickets" if priority else "tickets"
    if re.search(r"\balerts?\b", text):
        severity = next((value for value in ("critical", "warning", "info") if re.search(rf"\b{value}\b", text)), None)
        return f"{severity} alerts" if severity else "alerts"
    if re.search(r"\btasks?\b", text):
        return "onboarding tasks" if re.search(r"\bonboard", text) else "tasks"
    if re.search(r"\bwarrant", text):
        return "expired device warranties"
    if re.search(r"\bdevices?\b|\bservers?\b", text):
        return "offline devices" if re.search(r"\boffline\b", text) else "devices"
    return ""


def hybrid_parts(question: str) -> tuple[str, str] | None:
    for match in re.finditer(r"\band\s+(?=(?:what(?:'s| is| are)?|how|when|which|do we)\b)", question, re.IGNORECASE):
        documentation = question[match.end():].strip()
        if not re.search(r"\b(escalat\w*|procedur\w*|polic\w*|playbook\w*|steps?|guidelin\w*|handle|respond)\b",
                         documentation, re.IGNORECASE):
            continue
        live_question = question[:match.start()].strip(" ,?;\t\n")
        live_answer = answer_live_question(live_question)
        if live_answer is None:
            continue
        context = live_question_context(live_question)
        if context and not re.search(r"\b(tickets?|issues?|alerts?|tasks?|devices?|warrant\w*|servers?)\b",
                                     documentation, re.IGNORECASE):
            documentation = documentation.rstrip(" ?.!") + f" for {context}?"
        return live_answer, documentation
    return None


def asks_documented_overdue_tasks(question: str) -> bool:
    text = question.casefold()
    return bool(
        re.search(r"\b(clients?|companies|customers?)\b", text)
        and re.search(r"\btasks?\b", text)
        and re.search(r"\b(overdue|past[ -]?due|late)\b", text)
        and re.search(r"\b(documentation|documents?|docs|procedur\w*|process plans?|sops?)\b", text)
    )


def combine_answers(question: str, live_answer: str, documented: AskResponse) -> AskResponse:
    return AskResponse(
        question=question,
        answer=live_answer + "\n\nDocumentation context:\n" + documented.answer
               + "\n\nClient-specific due dates and completion states come from the sandbox task records.",
        sources=documented.sources,
        related_references=documented.related_references,
        status="hybrid" if documented.status == "answered" else "partial",
        model=documented.model,
        process_plan=documented.process_plan,
    )


def answer_question(request: AskRequest) -> AskResponse:
    question = request.question.strip()
    if len(question) < 3:
        raise ValueError("Question must contain at least 3 non-space characters")

    if asks_documented_overdue_tasks(question):
        live_answer = clients_with_overdue_tasks(only_onboarding=True)
        documented = answer_document_question(request.model_copy(update={
            "question": "What does the standard new-client procedure require for task due dates, "
                        "kickoff, monitoring deployment, backup setup, restore testing, and the "
                        "30-day review? Does it specify exact client dates?",
        }))
        return combine_answers(question, live_answer, documented)

    hybrid = hybrid_parts(question)
    if hybrid:
        live_answer, documentation_question = hybrid
        documented = answer_document_question(request.model_copy(update={"question": documentation_question}))
        return AskResponse(
            question=question,
            answer=live_answer + "\n\nFrom documentation:\n" + documented.answer,
            sources=documented.sources,
            related_references=documented.related_references,
            status="hybrid" if documented.status == "answered" else "partial",
            model=documented.model,
            process_plan=documented.process_plan,
        )

    live_answer = answer_live_question(question)
    if live_answer is not None:
        return AskResponse(
            question=question,
            answer=live_answer,
            sources=[],
            related_references=[],
            status="live_data",
        )

    return answer_document_question(request)


def answer_document_question(request: AskRequest) -> AskResponse:
    question = request.question.strip()

    # Semantic search already separates primary and Related chunks.
    hits = search_documents(
        question,
        limit=request.primary_limit,
        related_limit=request.related_limit,
        min_similarity=None,  # No arbitrary cutoff for observed 0.4-0.6 matches.
    )

    related = [RelatedReference(
        chunk_id=r["chunk_id"],
        document_title=r["document_title"],
        source_path=r.get("source_path"),
        chunk_index=r["chunk_index"],
        similarity=r["similarity"],
    ) for r in hits["related_results"]]

    context, sources = build_context(hits["primary_results"])
    if not sources:
        return AskResponse(
            question=question,
            answer="I couldn't find primary documentation to support an answer. Try a more specific question or import additional documents.",
            sources=[],
            related_references=related,
            status="insufficient_evidence",
        )

    client = make_client(timeout=45.0, max_retries=2)
    onboarding = documented_onboarding(question, sources)
    prompt = (
        f"USER QUESTION:\n{question}\n\n"
        f"PRIMARY SOURCE EXCERPTS:\n{context}\n\n"
        "Only cite the numbered primary source excerpts above. "
        "Do not use related-reference listings as evidence."
    )
    if onboarding:
        prompt += (
            "\nThis is a documented onboarding workflow. Provide a process plan "
            "draft with milestones and tasks. Leave company_name blank if unnamed."
        )

    def generate(extra_instruction: str = "") -> ModelReply:
        response = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS + extra_instruction,
            input=prompt,
            text=REPLY_FORMAT,
            max_output_tokens=2400,
            store=False,
        )
        return ModelReply.model_validate_json(response.output_text or "")

    # Remove unsupported numeric source citations (e.g. the model invents [99]).
    allowed = {s.citation for s in sources}

    def prepare(reply: ModelReply) -> tuple[str, SuggestedProcessPlan | None]:
        def clean(text: str) -> str:
            return re.sub(
                r"\[(\d+)\]",
                lambda match: match.group(0) if match.group(0) in allowed else "",
                text.strip(),
            )

        intro = clean(reply.answer)
        steps = [step for item in reply.steps if (step := re.sub(r"^\d+[.)]\s*", "", clean(item)))]
        note = clean(reply.closing_note)
        answer = "\n\n".join(part for part in (
            intro,
            "\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1)),
            note,
        ) if part)
        if not answer:
            raise RuntimeError("Generation returned no text")
        return answer, usable_plan(reply, question, answer, sources, onboarding)

    reply = generate()
    answer, process_plan = prepare(reply)
    if onboarding and process_plan is None:
        retry = generate("\nFor this documented onboarding request, set suggest_process_plan to true and populate process_plan with concrete steps. Put the procedure's actions in steps, not answer.")
        retry_answer, retry_plan = prepare(retry)
        if retry_plan is not None:
            reply, answer, process_plan = retry, retry_answer, retry_plan
    sequence_words = re.findall(r"\b(first|then|next|finally)\b", reply.answer, re.IGNORECASE)
    if not reply.steps and (process_plan is not None or len(sequence_words) >= 2):
        retry = generate("\nYour answer describes a procedure. Put each documented action in the steps array in order. Keep answer to a short introduction and closing_note to caveats.")
        if retry.steps:
            answer, retry_plan = prepare(retry)
            process_plan = retry_plan or process_plan
    return AskResponse(
        question=question,
        answer=answer,
        sources=sources,
        related_references=related,
        status="answered",
        model=MODEL,
        process_plan=process_plan,
    )


app = FastAPI(title="Omni Brain RAG API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    try:
        return answer_question(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LiveDataError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("RAG request failed")
        raise HTTPException(
            status_code=502,
            detail="RAG processing failed; check server logs and API/database connectivity.",
        ) from exc
