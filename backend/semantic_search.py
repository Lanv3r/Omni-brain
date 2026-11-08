import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from pgvector import Vector
from pgvector.psycopg import register_vector

#Load environment variables from the project root
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

client = OpenAI(timeout=30.0, max_retries=2)


#Convert the question to an embedding
def embed_question(question):
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=question,
        dimensions=EMBEDDING_DIMENSIONS
    )

    return response.data[0].embedding


#Search PostgreSQL for similar document chunks
def search_documents(question, limit=5):
    if not question.strip():
        raise ValueError("Question cannot be empty")

    if not 1 <= limit <= 20:
        raise ValueError("Limit must be between 1 and 20")

    question_vector = Vector(embed_question(question))

    with psycopg.connect(
        host="127.0.0.1",
        port=5432,
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD"),
        connect_timeout=5
    ) as conn:

        register_vector(conn)

        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    dc.id,
                    dc.content,
                    d.title,
                    d.source_path,
                    dc.chunk_index,
                    1 - (dc.embedding <=> %s) AS similarity
                FROM document_chunks dc
                JOIN documents d
                    ON dc.document_id = d.id
                WHERE dc.embedding IS NOT NULL
                ORDER BY dc.embedding <=> %s
                LIMIT %s
                """,
                (
                    question_vector,
                    question_vector,
                    limit
                )
            )

            rows = cur.fetchall()

    #Return structured search results
    return [
        {
            "chunk_id": row[0],
            "content": row[1],
            "document_title": row[2],
            "source_path": row[3],
            "chunk_index": row[4],
            "similarity": float(row[5])
        }
        for row in rows
    ]


#Test retrieval from the terminal
if __name__ == "__main__":
    question = " ".join(sys.argv[1:]).strip()

    if not question:
        question = input("Enter your question: ").strip()

    results = search_documents(question)

    if not results:
        print("No embedded document chunks found.")

    for index, result in enumerate(results, start=1):
        print(f"\n--- RESULT {index} ---")
        print(f"Document: {result['document_title']}")
        print(f"Source: {result['source_path']}")
        print(f"Chunk: {result['chunk_index']}")
        print(f"Similarity: {result['similarity']:.3f}")
        print(f"\n{result['content']}")