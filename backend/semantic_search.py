"""Semantic document retrieval with separate primary and related results.

Usage (from the project root, with your virtual environment activated):
    python backend/semantic_search.py "How do I troubleshoot DNS failures?"
    python backend/semantic_search.py "How do I troubleshoot DNS failures?" --limit 5 --related-limit 2

Environment variables in the project-root .env:
    OPENAI_API_KEY=...
    POSTGRES_USER=jonat
    POSTGRES_PASSWORD=...
    POSTGRES_DB=omni_brain

Dependencies:
    python -m pip install openai "psycopg[binary]" pgvector python-dotenv
"""

import argparse
import os
import re
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from pgvector import Vector
from pgvector.psycopg import register_vector

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
PAGE_SIZE = 100
MAX_CANDIDATES = 2000

# Match Markdown heading lines, not mentions of "related" in ordinary prose.
# Handles e.g. "## Related", "### Related Documents", "## Related Document".
RELATED_HEADING = re.compile(
    r"^#{1,6}[ \t]+Related(?:[ \t]+Documents?)?[ \t]*$",
    flags=re.IGNORECASE | re.MULTILINE,
)


def is_related_chunk(content: str) -> bool:
    """Classify a chunk as supplemental if it has a Related heading."""
    return bool(RELATED_HEADING.search(content))


def embed_question(client: OpenAI, question: str) -> Vector:
    """Embed a question with the *same* model/dimensions used for chunks."""
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    values = response.data[0].embedding
    if len(values) != EMBEDDING_DIMENSIONS:
        raise ValueError(f"Expected {EMBEDDING_DIMENSIONS} dimensions, got {len(values)}")
    return Vector(values)


def search_documents(
    question: str,
    limit: int = 5,
    related_limit: int = 2,
    min_similarity: float | None = None,
) -> dict:
    """Find up to `limit` primary chunks PLUS `related_limit` related chunks.

    Results are ranked by descending cosine similarity within each category.
    `min_similarity=None` avoids rejecting relevant 0.4-0.6 matches.
    Pagination continues until both categories are full, results run out, or
    MAX_CANDIDATES is reached. It never sends retrieved content to a chat LLM.
    """
    question = question.strip()
    if not question:
        raise ValueError("Question cannot be empty")
    if not 1 <= limit <= 20:
        raise ValueError("limit must be between 1 and 20")
    if not 0 <= related_limit <= 20:
        raise ValueError("related_limit must be between 0 and 20")
    if min_similarity is not None and not -1 <= min_similarity <= 1:
        raise ValueError("min_similarity must be between -1 and 1")

    client = OpenAI(timeout=30.0, max_retries=2)
    question_vector = embed_question(client, question)

    primary: list[dict] = []
    related: list[dict] = []
    inspected = 0
    exhausted = False

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        connect_timeout=5,
    ) as conn:
        register_vector(conn)
        with conn.cursor() as cur:
            while inspected < MAX_CANDIDATES:
                fetch_size = min(PAGE_SIZE, MAX_CANDIDATES - inspected)
                cur.execute(
                    """
                    SELECT
                        dc.id,
                        dc.content,
                        d.title,
                        d.source_path,
                        dc.chunk_index,
                        1 - (dc.embedding <=> %s) AS similarity
                    FROM document_chunks AS dc
                    JOIN documents AS d ON d.id = dc.document_id
                    WHERE dc.embedding IS NOT NULL
                    ORDER BY dc.embedding <=> %s, dc.id
                    LIMIT %s OFFSET %s
                    """,
                    (question_vector, question_vector, fetch_size, inspected),
                )
                rows = cur.fetchall()
                if not rows:
                    exhausted = True
                    break

                for chunk_id, content, title, source_path, chunk_index, similarity in rows:
                    result = {
                        "chunk_id": chunk_id,
                        "content": content,
                        "document_title": title,
                        "source_path": source_path,
                        "chunk_index": chunk_index,
                        "similarity": float(similarity),
                    }
                    if min_similarity is not None and result["similarity"] < min_similarity:
                        # Rows are sorted descending, so no later result can pass.
                        exhausted = True
                        break

                    if is_related_chunk(content):
                        if len(related) < related_limit:
                            related.append(result)
                    elif len(primary) < limit:
                        primary.append(result)

                    if len(primary) == limit and len(related) == related_limit:
                        break

                inspected += len(rows)
                if exhausted or (len(primary) == limit and len(related) == related_limit):
                    break
                if len(rows) < fetch_size:
                    exhausted = True
                    break

    return {
        "question": question,
        "primary_results": primary,
        "related_results": related,
        "primary_count": len(primary),
        "related_count": len(related),
        "candidates_examined": inspected,
        "candidate_cap_reached": not exhausted and inspected >= MAX_CANDIDATES,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Search Omni Brain document chunks")
    parser.add_argument("question", nargs="*", help="Question to search for")
    parser.add_argument("--limit", type=int, default=5, help="Primary chunk slots (default: 5)")
    parser.add_argument("--related-limit", type=int, default=2, help="Extra related slots (default: 2)")
    parser.add_argument("--min-similarity", type=float, default=None, help="Optional cosine-similarity cutoff")
    args = parser.parse_args()

    question = " ".join(args.question).strip() or input("Enter your question: ").strip()
    results = search_documents(question, args.limit, args.related_limit, args.min_similarity)

    for group, label in (("primary_results", "PRIMARY"), ("related_results", "RELATED (supplemental)")):
        print(f"\n=== {label}: {len(results[group])} ===")
        for idx, item in enumerate(results[group], start=1):
            print(f"\n[{idx}] {item['document_title']} | similarity={item['similarity']:.3f}")
            print(f"Source: {item['source_path']} | chunk {item['chunk_index']} | id {item['chunk_id']}")
            print(item["content"])

    print(f"\nPrimary: {results['primary_count']} | Related: {results['related_count']}")
    if results["candidate_cap_reached"]:
        print("Note: candidate scan limit reached; additional matches may exist.")


if __name__ == "__main__":
    main()
