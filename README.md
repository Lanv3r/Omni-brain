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
The Command Center's **Process plans** card opens guided checklists for
general and CPA-firm client onboarding, new-user account setup, workstation
setup, and employee offboarding. Their steps load from the practice API's
Markdown guides; progress is saved in the current browser and does not
change external systems.
The ticket queue loads the latest 100 practice tickets and joins each ticket
to its client record. Ticket details show client industry, plans, location,
employee count, parent company, and requester. Connected tickets are synced
into local SQLite when fetched so they can use the existing linked-task flow.

   The backend exposes JSON endpoints for dashboard data:

   - `GET /api/v1/tickets`
   - `GET /api/v1/tasks`
   - `GET /api/v1/tickets/{ticket_id}/tasks`
   - `POST /api/v1/tickets/{ticket_id}/tasks` (creates a linked task)
   - `GET /api/v1/alerts`
   - `GET /api/v1/devices`
   - `GET /api/v1/summary`
   - `GET /api/v1/health`
   - `GET /api/v1/practice/clients`
   - `GET /api/v1/practice/tickets`
   - `GET /api/v1/practice/tickets/{ticket_id}`
   - `GET /process-plans`

   Ticket detail pages can create tasks linked to their ticket. Linked tasks
   appear in the ticket details and in the Tasks queue. This workflow requires
   the backend to be running and the example database to have been seeded.
   The ticket task form can also request up to three Gemini task suggestions.
   The ticket subject and description are sent to OpenRouter only when the
   user clicks **Suggest tasks with AI**; suggestions must be reviewed and
   explicitly added to the form before a task is created.
   - `POST /api/v1/tickets/{ticket_id}/task-suggestions`

The root `.env` is ignored by Git. Never put API keys in frontend files or commit
the `.env` file.