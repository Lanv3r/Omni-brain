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
   py -m uvicorn backend.main:app --reload --port 8000
   ```
   The backend creates its local SQLite database at
   `backend/data/omni_brain.sqlite3` on startup. To load the dashboard's example
   records into it, run this once from the repository root:

   ```powershell
   py -m backend.seed
   ```

   Set `DATABASE_PATH` in `.env` to use a different SQLite file.
4. Start the frontend preview in a second terminal:

   ```powershell
   node frontend/server.js
   ```
5. Open <http://127.0.0.1:3000/Html-side/Hackathon/index.html> and choose
   **Knowledge Base**. Questions are answered using relevant Markdown documents
   from the practice API, with source paths shown below each answer.

   The backend also exposes read-only JSON endpoints for the dashboard data:

   - `GET /api/v1/tickets`
   - `GET /api/v1/tasks`
   - `GET /api/v1/alerts`
   - `GET /api/v1/devices`
   - `GET /api/v1/summary`
   - `GET /api/v1/health`

   These endpoints read from SQLite. The dashboard pages still display their
   existing example rows; connecting the UI to these endpoints can be done as a
   separate step.

The root `.env` is ignored by Git. Never put API keys in frontend files or commit
the `.env` file.