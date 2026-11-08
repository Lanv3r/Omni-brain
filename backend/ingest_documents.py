"""Ingest Omni Brain Markdown knowledge-base files into PostgreSQL.

Run from project root:
    python backend/ingest_documents.py --dry-run
    python backend/ingest_documents.py
    python backend/ingest_documents.py --all

Requires: requests, psycopg[binary], python-dotenv, tiktoken, markdown-it-py.
SQL prerequisite: ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_hash TEXT;
"""

import argparse
import hashlib
import os
import re
from pathlib import Path

import psycopg
import requests
import tiktoken
from dotenv import load_dotenv
from markdown_it import MarkdownIt

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

API_URL = os.getenv("OMNI_API_BASE", "http://localhost:8080").rstrip("/")
MAX_TOKENS = 600
OVERLAP_TOKENS = 75
CHUNKER_VERSION = "markdown-v2"
ENCODER = tiktoken.encoding_for_model("text-embedding-3-small")
PARSER = MarkdownIt("default")


def count_tokens(value: str) -> int:
    return len(ENCODER.encode(value))


def heading_prefix(headings: list[tuple[int, str]]) -> str:
    return "\n".join("#" * level + " " + title for level, title in headings)


def render(headings: list[tuple[int, str]], blocks: list[str]) -> str:
    return "\n\n".join(filter(None, [heading_prefix(headings), *blocks]))


def split_long_prose(text: str, allowance: int) -> list[str]:
    """Split oversized prose at sentences, then words; never silently truncate."""
    if allowance <= 0:
        raise ValueError("Heading context is larger than the chunk size")

    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    pieces = []
    current = ""
    for sentence in sentences:
        if count_tokens(sentence) > allowance:
            # Extremely long sentence: fall back to whole-word splits.
            words = sentence.split()
            for word in words:
                if count_tokens(word) > allowance:
                    raise ValueError("One word exceeds the chunk size")
                candidate = (current + " " + word).strip()
                if current and count_tokens(candidate) > allowance:
                    pieces.append(current)
                    current = word
                else:
                    current = candidate
            continue

        candidate = (current + " " + sentence).strip()
        if current and count_tokens(candidate) > allowance:
            pieces.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        pieces.append(current)
    return pieces


def markdown_sections(text: str):
    """Use a Markdown parser to preserve fences, lists, quotes and heading hierarchy."""
    lines = text.splitlines(keepends=True)
    tokens = PARSER.parse(text)
    sections = []
    headings: list[tuple[int, str]] = []
    blocks: list[tuple[str, str]] = []

    block_starts = {
        "paragraph_open", "fence", "code_block", "bullet_list_open",
        "ordered_list_open", "blockquote_open", "table_open", "html_block", "hr",
    }

    for index, token in enumerate(tokens):
        if token.level != 0 or token.map is None:
            continue

        if token.type == "heading_open":
            if blocks:
                sections.append((headings.copy(), blocks))
                blocks = []

            level = int(token.tag[1])
            title = tokens[index + 1].content.strip()
            headings = [(n, t) for n, t in headings if n < level]
            headings.append((level, title))

        elif token.type in block_starts:
            start, end = token.map
            literal = "".join(lines[start:end]).strip()
            if literal:
                blocks.append((token.type, literal))

    if blocks:
        sections.append((headings.copy(), blocks))
    return sections


def chunk_text(text: str) -> list[str]:
    chunks = []
    for headings, blocks in markdown_sections(text):
        allowance = MAX_TOKENS - count_tokens(heading_prefix(headings)) - 8
        if allowance <= 0:
            raise ValueError("Heading hierarchy is too long for a chunk")

        units = []
        for kind, block in blocks:
            if count_tokens(block) > allowance and kind == "paragraph_open":
                units.extend(split_long_prose(block, allowance))
            else:
                # Preserve code blocks and lists as atomic units.
                # An unusually large atomic unit may exceed MAX_TOKENS.
                if count_tokens(block) > allowance:
                    print(f"WARNING: Oversized {kind} block ({count_tokens(block)} tokens); preserved intact")
                units.append(block)

        current = []
        for unit in units:
            if current and count_tokens(render(headings, current + [unit])) > MAX_TOKENS:
                chunks.append(render(headings, current))
                overlap = [current[-1]] if count_tokens(current[-1]) <= OVERLAP_TOKENS else []
                current = overlap if count_tokens(render(headings, overlap + [unit])) <= MAX_TOKENS else []
            current.append(unit)

        if current:
            chunks.append(render(headings, current))

    return chunks


def api_headers() -> dict[str, str]:
    key = os.getenv("OMNI_API_KEY")
    return {"Authorization": f"Bearer {key}"} if key else {}


def get_index() -> list[dict]:
    r = requests.get(f"{API_URL}/kb/index", headers=api_headers(), timeout=20)
    r.raise_for_status()
    return r.json()["files"]


def get_document(path: str) -> str:
    r = requests.get(
        f"{API_URL}/kb/file", params={"path": path},
        headers=api_headers(), timeout=20,
    )
    r.raise_for_status()
    return r.text


def save_document(title: str, path: str, text: str, chunks: list[str]) -> str:
    # Including the chunker version ensures rule changes trigger re-chunking.
    fingerprint = hashlib.sha256(
        (CHUNKER_VERSION + "\n" + text).encode("utf-8")
    ).hexdigest()
    source_path = f"kb/{path}"

    with psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB", "omni_brain"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        connect_timeout=5,
    ) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, content_hash FROM documents WHERE source_path = %s FOR UPDATE",
                (source_path,),
            )
            existing = cur.fetchone()
            if existing and existing[1] == fingerprint:
                return "unchanged"

            if existing:
                document_id = existing[0]
                cur.execute("DELETE FROM document_chunks WHERE document_id = %s", (document_id,))
                cur.execute(
                    "UPDATE documents SET title = %s, content_hash = %s WHERE id = %s",
                    (title, fingerprint, document_id),
                )
            else:
                cur.execute(
                    "INSERT INTO documents (title, source_path, content_hash) "
                    "VALUES (%s, %s, %s) RETURNING id",
                    (title, source_path, fingerprint),
                )
                document_id = cur.fetchone()[0]

            cur.executemany(
                "INSERT INTO document_chunks (document_id, chunk_index, content) "
                "VALUES (%s, %s, %s)",
                [(document_id, i, chunk) for i, chunk in enumerate(chunks)],
            )
    return f"saved document {document_id} with {len(chunks)} chunks"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true", help="Process every KB document")
    parser.add_argument("--dry-run", action="store_true", help="Inspect chunks without writing to PostgreSQL")
    args = parser.parse_args()

    documents = get_index()
    if not documents:
        print("No knowledge-base documents found")
        return

    selected = documents if args.all else documents[:1]
    for item in selected:
        path = item["path"]
        text = get_document(path)
        chunks = chunk_text(text)
        print(f"\n{path}: {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            print(f"  chunk {i}: {count_tokens(chunk)} tokens")
        if args.dry_run:
            for i, chunk in enumerate(chunks):
                print(f"\n--- Chunk {i} ---\n{chunk[:600]}")
        elif chunks:
            print(save_document(item["title"], path, text, chunks))
        else:
            print("WARNING: No content chunks generated; document not saved")


if __name__ == "__main__":
    main()
