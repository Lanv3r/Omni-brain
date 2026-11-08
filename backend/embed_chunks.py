
import argparse
import os
from pathlib import Path

import psycopg
import tiktoken
from dotenv import load_dotenv
from pgvector import Vector
from pgvector.psycopg import register_vector

from backend.ai_client import make_client, model_name

# ---------------- CONFIGURATION ----------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = model_name("text-embedding-3-small")
DIMENSIONS = 1536
MAX_INPUT_TOKENS = 8192

encoder = tiktoken.encoding_for_model("text-embedding-3-small")


# ---------------- DATABASE CONNECTION ----------------

def connect_db():
    conn = psycopg.connect(
        host=os.getenv("POSTGRES_HOST", "127.0.0.1"),
        port=int(os.getenv("POSTGRES_PORT", "5432")),
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        connect_timeout=5,
    )

    register_vector(conn)
    return conn


# ---------------- GET UNEMBEDDED CHUNKS ----------------

def get_chunks(conn, limit):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, content
            FROM document_chunks
            WHERE embedding IS NULL
              AND length(trim(content)) > 0
            ORDER BY id
            LIMIT %s
            """,
            (limit,)
        )

        return cur.fetchall()


# ---------------- VALIDATE TEXT ----------------

def validate_chunks(chunks):
    for chunk_id, content in chunks:
        token_count = len(encoder.encode(content))

        if token_count > MAX_INPUT_TOKENS:
            raise ValueError(
                f"Chunk {chunk_id} has {token_count} tokens. "
                "Re-chunk this document before embedding."
            )


# ---------------- GENERATE EMBEDDINGS ----------------

def generate_embeddings(client, chunks):
    texts = [content for _, content in chunks]

    response = client.embeddings.create(
        model=MODEL,
        input=texts,
        dimensions=DIMENSIONS,
        encoding_format="float",
    )

    # Map embeddings by their returned input index
    vectors = {
        item.index: item.embedding
        for item in response.data
    }

    if len(vectors) != len(chunks):
        raise ValueError("Embedding response count mismatch")

    ordered_vectors = []

    for i in range(len(chunks)):
        if i not in vectors:
            raise ValueError(f"Missing embedding for index {i}")

        vector = vectors[i]

        if len(vector) != DIMENSIONS:
            raise ValueError(
                f"Expected {DIMENSIONS} dimensions, "
                f"received {len(vector)}"
            )

        ordered_vectors.append(vector)

    return ordered_vectors, response.usage.total_tokens


# ---------------- STORE EMBEDDINGS ----------------

def save_embeddings(conn, chunks, vectors):
    saved = 0

    with conn.cursor() as cur:
        for (chunk_id, _), vector in zip(chunks, vectors):
            cur.execute(
                """
                UPDATE document_chunks
                SET embedding = %s
                WHERE id = %s
                  AND embedding IS NULL
                """,
                (Vector(vector), chunk_id),
            )
            saved += cur.rowcount

    conn.commit()
    return saved


# ---------------- MAIN PROCESS ----------------

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--limit", type=int, default=10
    )
    parser.add_argument(
        "--batch-size", type=int, default=10
    )
    parser.add_argument(
        "--dry-run", action="store_true"
    )

    parser.add_argument(
        "--all", action="store_true", help="Embed every unembedded chunk"
    )

    args = parser.parse_args()

    if args.limit < 1 or args.batch_size < 1:
        parser.error("limit and batch-size must be positive")

    client = None

    if not args.dry_run:
        client = make_client(
            timeout=30.0,
            max_retries=2,
        )

    processed = 0
    total_tokens = 0

    with connect_db() as conn:
        while True:
            remaining = args.limit - processed
            if not args.all and remaining <= 0:
                break
            batch = get_chunks(conn, args.batch_size if args.all else min(args.batch_size, remaining))
            if not batch:
                break

            validate_chunks(batch)
            print(f"Processing batch of {len(batch)} chunks...")

            if args.dry_run:
                for chunk_id, content in batch:
                    print(f"Chunk {chunk_id}: {len(encoder.encode(content))} tokens")
                break

            vectors, used_tokens = generate_embeddings(client, batch)
            saved = save_embeddings(conn, batch, vectors)
            processed += saved
            total_tokens += used_tokens
            print(f"Saved {saved} embeddings.")

    print("\nFinished!")
    print(f"New embeddings stored: {processed}")
    print(f"API tokens used: {total_tokens}")


if __name__ == "__main__":
    main()
