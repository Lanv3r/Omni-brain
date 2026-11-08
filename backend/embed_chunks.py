import os
import psycopg
from dotenv import load_dotenv
from openai import OpenAI
from pgvector.psycopg import register_vector

load_dotenv()

client = OpenAI()

# Connect to your local PostgreSQL database
with psycopg.connect(
    host="localhost",
    port=5432,
    dbname=os.getenv("POSTGRES_DB"),
    user=os.getenv("POSTGRES_USER"),
    password=os.getenv("POSTGRES_PASSWORD")
) as conn:

    register_vector(conn)

    # Retrieve chunks that have not been embedded
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, content
            FROM document_chunks
            WHERE embedding IS NULL
              AND length(trim(content)) > 0
            ORDER BY id
            LIMIT 10
        """)

        chunks = cur.fetchall()

    # Generate and store an embedding for each chunk
    for chunk_id, content in chunks:

        response = client.embeddings.create(
            model="text-embedding-3-small",
            input=content
        )

        embedding = response.data[0].embedding

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE document_chunks
                SET embedding = %s
                WHERE id = %s
            """, (embedding, chunk_id))

        conn.commit()

        print(f"Embedded chunk {chunk_id}")

print("Embedding process complete!")