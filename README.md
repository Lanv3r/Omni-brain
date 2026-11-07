# Omni-brain

## Local knowledge-base assistant

1. Start the practice API in Docker:

   ```powershell
   docker run --rm -p 8080:8080 ghcr.io/jeremyheslop/omni-brain-mock:latest
   ```

   If the practice API was started with its optional `API_KEY`, set the same value as
   `PRACTICE_API_KEY` in the root `.env`. Otherwise, leave it blank.
2. Set `OPENROUTER_API_KEY` in the root `.env`. The backend uses
   `google/gemini-2.5-flash` by default; `OPENROUTER_MODEL` can override it.
3. Install and start the backend from the repository root:

   ```powershell
   py -m pip install -r backend/requirements.txt
   py -m uvicorn main:app --app-dir backend --reload --port 8000
   ```
4. Start the frontend preview in a second terminal:

   ```powershell
   node frontend/server.js
   ```
5. Open <http://127.0.0.1:3000/Html-side/Hackathon/index.html> and choose
   **Knowledge Base**. Questions are answered using relevant Markdown documents
   from the practice API, with source paths shown below each answer.

The root `.env` is ignored by Git. Never put API keys in frontend files or commit
the `.env` file.