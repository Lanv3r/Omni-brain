import os
import re
import textwrap

import requests
import psycopg
from dotenv import load_dotenv

load_dotenv()

API_URL = "http://localhost:8080"
MAX_CHARS = 1800


#Retrieve a document from Omni Brain
def fetch_document():
    headers = {}

    if os.getenv("API_KEY"):
        headers["Authorization"] = (
            f"Bearer {os.getenv('API_KEY')}"
        )

    response = requests.get(
        f"{API_URL}/kb/index",
        headers=headers,
        timeout=15
    )
    response.raise_for_status()

    files = response.json()["files"]

    if not files:
        raise ValueError("No documents found in knowledge base")

    # Start with just the first document
    document = files[0]
    path = document["path"]

    response = requests.get(
        f"{API_URL}/kb/file",
        params={"path": path},
        headers=headers,
        timeout=15
    )
    response.raise_for_status()

    return document["title"], path, response.text


#Split a document into chunks
def chunk_text(text):
    chunks = []
    heading = ""
    current = ""

    def add_text(piece, heading, current):
        prefix = heading + "\n\n" if heading else ""

        if not current:
            return prefix + piece

        candidate = current + "\n\n" + piece

        if len(candidate) > MAX_CHARS:
            chunks.append(current)
            return prefix + piece

        return candidate

    # Process headings and paragraphs in order
    blocks = re.split(r"\n\s*\n", text.strip())

    for block in blocks:
        block = block.strip()

        if not block:
            continue

        # Detect a Markdown heading
        if re.fullmatch(r"#{1,6}\s+.+", block):
            if current:
                chunks.append(current)
                current = ""

            heading = block
            continue

        # Split unusually large paragraphs
        room = MAX_CHARS - len(heading) - 10

        if room < 200:
            raise ValueError("Heading too long")

        pieces = textwrap.wrap(
            block,
            width=room,
            break_long_words=True,
            break_on_hyphens=False
        )

        for piece in pieces:
            current = add_text(piece, heading, current)

    if current:
        chunks.append(current)

    return chunks


#Insert document and chunks
def save_document(title, path, chunks):
    print("DEBUG: ENTERED SAVE DOC()",flush=True)
    source_path = f"kb/{path}"

    with psycopg.connect(
        host="localhost",
        port=5432,
        dbname=os.getenv("POSTGRES_DB"),
        user=os.getenv("POSTGRES_USER"),
        password=os.getenv("POSTGRES_PASSWORD")
    ) as conn:

        with conn.cursor() as cur:
            # Find a previous import of this document
            cur.execute(
                """
                SELECT id FROM documents
                WHERE source_path = %s
                LIMIT 1
                FOR UPDATE
                """,
                (source_path,)
            )

            row = cur.fetchone()

            if row:
                document_id = row[0]

                # Replace existing chunks when re-importing
                cur.execute(
                    """
                    DELETE FROM document_chunks
                    WHERE document_id = %s
                    """,
                    (document_id,)
                )

                cur.execute(
                    """
                    UPDATE documents
                    SET title = %s
                    WHERE id = %s
                    """,
                    (title, document_id)
                )

            else:
                cur.execute(
                    """
                    INSERT INTO documents (title, source_path)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (title, source_path)
                )

                document_id = cur.fetchone()[0]

            # Insert each chunk
            for index, chunk in enumerate(chunks):
                cur.execute(
                    """
                    INSERT INTO document_chunks
                        (document_id, chunk_index, content)
                    VALUES (%s, %s, %s)
                    """,
                    (document_id, index, chunk)
                )

    return document_id


# STEP 4: Run the pipeline
if __name__ == "__main__":
    title, path, text = fetch_document()

    print(f"Document: {title}")
    print(f"Source: {path}")

    chunks = chunk_text(text)

    if not chunks:
        raise ValueError("Document produced no chunks")

    print(f"Generated {len(chunks)} chunks")

    for index, chunk in enumerate(chunks):
        print(f"Chunk {index}: {len(chunk)} characters")

    document_id = save_document(title, path, chunks)

    print(f"Saved document {document_id} to PostgreSQL")