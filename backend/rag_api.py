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
10. If checklists or numerated steps are present, display them to the user 
    if deemed relevant by previous instructions given."""


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


class AskResponse(BaseModel):
    question: str
    answer: str
    sources: list[Source]
    related_references: list[RelatedReference]
    status: str
    model: str | None = None


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


def answer_question(request: AskRequest) -> AskResponse:
    question = request.question.strip()
    if len(question) < 3:
        raise ValueError("Question must contain at least 3 non-space characters")

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
    response = client.responses.create(
        model=MODEL,
        instructions=INSTRUCTIONS,
        input=(
            f"USER QUESTION:\n{question}\n\n"
            f"PRIMARY SOURCE EXCERPTS:\n{context}\n\n"
            "Only cite the numbered primary source excerpts above. "
            "Do not use related-reference listings as evidence."
        ),
        max_output_tokens=900,
        store=False,
    )
    answer = (response.output_text or "").strip()
    if not answer:
        raise RuntimeError("Generation returned no text")

    # Remove unsupported numeric source citations (e.g. the model invents [99]).
    allowed = {s.citation for s in sources}
    answer = re.sub(
        r"\[(\d+)\]",
        lambda match: match.group(0) if match.group(0) in allowed else "",
        answer,
    )
    return AskResponse(
        question=question,
        answer=answer,
        sources=sources,
        related_references=related,
        status="answered",
        model=MODEL,
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
    except Exception as exc:
        logger.exception("RAG request failed")
        raise HTTPException(
            status_code=502,
            detail="RAG processing failed; check server logs and API/database connectivity.",
        ) from exc
