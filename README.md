# Omni-brain

Milestones added to existing process plans are stored in `backend/process_plans.sqlite3`. Tasks under those milestones are created against the job in Accelo, where they receive numeric task IDs; the database keeps their milestone grouping in the process planner. Tasks saved locally by the earlier version can be synced with Accelo using the plan's Save changes button. Set `PROCESS_PLAN_DB` to use a different database path and keep it on persistent storage when running the backend in a container. New plans remain temporary because the connected API has no job-creation endpoint.

The Current employee selector is stored in this browser and drives My Assignments. Tickets and Tasks support selecting multiple assignees, including Unassigned. The employee selector is a convenience identity, not access control.
