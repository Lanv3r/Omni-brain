# Omni-brain

## Start everything with Docker

For the first run, copy `.env.example` to `.env` and set `OPENAI_API_KEY` to your own OpenAI or OpenRouter API key. If using OpenRouter, also set `OPENAI_BASE_URL=https://openrouter.ai/api/v1`. The app automatically uses OpenRouter's `openai/` model slugs for answers and embeddings. Docker Desktop must be running. Then run from this directory:

```bash
docker compose up --build
```

Open http://127.0.0.1:3000. The backend is at http://127.0.0.1:8000. PostgreSQL and the mock data API are available to other Compose services by their service names; they do not need host ports. Subsequent starts can use `docker compose up`.

Compose starts the mock API, PostgreSQL with pgvector, the AI table initialization, an indexing job, the FastAPI backend, and the Node frontend. The indexing job imports the mock API's knowledge-base documents and embeds any new chunks. It skips unchanged documents on later starts. The AI Assistant sends each question to `POST /ai/ask` on the backend. The backend searches the indexed documents, calls the configured AI provider, and returns the answer. Each question is independent; chat history is displayed in the browser but is not sent as context.

Indexing sends knowledge-base text to the configured AI provider for embeddings; asking a question sends retrieved excerpts for the answer. Both operations use the API key and incur API usage.

When the AI Assistant can build an onboarding plan from the documentation, it offers a **Create a process plan** button. This opens editable name, company, milestone, and task fields in Process plans. Assignees and deadlines are left for the user to choose. Clicking **Create plan** creates a temporary plan for this browser session; the connected API has no job-creation endpoint.

PostgreSQL data persists in the `postgres_data` Docker volume. The process planner's separate SQLite database persists in the `process_plan_data` volume; on the first start, Compose copies an existing `backend/process_plans.sqlite3` into that volume if one exists. `.env` and SQLite data stay out of Git. Each developer needs their own `.env` file and Docker volumes. `docker compose down` stops the services without deleting data; `docker compose down -v` deletes both volumes.

If startup fails, check `docker compose logs knowledge-index` for a missing or invalid API key, mock API errors, or document ingestion errors.

Milestones added to existing process plans are stored in SQLite (`backend/process_plans.sqlite3` when running outside Docker, or the `process_plan_data` volume in Docker). Tasks under those milestones are created against the job in Accelo, where they receive numeric task IDs; SQLite keeps their milestone grouping in the process planner. Tasks saved locally by the earlier version can be synced with Accelo using the plan's Save changes button. New plans remain temporary because the connected API has no job-creation endpoint.

The Current employee selector is stored in this browser and drives My Assignments. Tickets and Tasks support selecting multiple assignees, including Unassigned. The employee selector is a convenience identity, not access control.
