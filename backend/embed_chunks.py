
import argparse
import os
from pathlib import Path

import psycopg
import tiktoken
from dotenv import load_dotenv
from openai import OpenAI
from pgvector import Vector
from pgvector.psycopg import register_vector

# ---------------- CONFIGURATION ----------------

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MODEL = "text-embedding-3-small"
DIMENSIONS = 1536
MAX_INPUT_TOKENS = 8192

encoder = tiktoken.encoding_for_model(MODEL)


# ---------------- DATABASE CONNECTION ----------------

def connect_db():
    conn = psycopg.connect(
        host="127.0.0.1",
        port=5432,
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

    args = parser.parse_args()

    if args.limit < 1 or args.batch_size < 1:
        parser.error("limit and batch-size must be positive")

    client = None

    if not args.dry_run:
        client = OpenAI(
            timeout=30.0,
            max_retries=2,
        )

    processed = 0
    total_tokens = 0

    with connect_db() as conn:
        chunks = get_chunks(conn, args.limit)

        if not chunks:
            print("No unembedded chunks found.")
            return

        print(f"Found {len(chunks)} chunks.")

        for start in range(0, len(chunks), args.batch_size):
            batch = chunks[start:start + args.batch_size]

            validate_chunks(batch)

            print(
                f"Processing batch of {len(batch)} chunks..."
            )

            if args.dry_run:
                for chunk_id, content in batch:
                    tokens = len(encoder.encode(content))
                    print(f"Chunk {chunk_id}: {tokens} tokens")
                continue

            vectors, used_tokens = generate_embeddings(
                client, batch
            )

            saved = save_embeddings(conn, batch, vectors)

            processed += saved
            total_tokens += used_tokens

            print(f"Saved {saved} embeddings.")

    print("\nFinished!")
    print(f"New embeddings stored: {processed}")
    print(f"API tokens used: {total_tokens}")


if __name__ == "__main__":
    main()