import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
    allow_methods=["GET", "POST", "PUT"],
    allow_headers=["Content-Type"],
)
issues_url = os.getenv(
    "ISSUES_URL",
    "http://127.0.0.1:8080/api/v0/issues",
)
companies_url = os.getenv(
    "COMPANIES_URL",
    "http://127.0.0.1:8080/api/v0/companies",
)
alerts_url = os.getenv(
    "ALERTS_URL",
    "http://127.0.0.1:8080/ncentral/alerts",
)
devices_url = os.getenv(
    "DEVICES_URL",
    "http://127.0.0.1:8080/ncentral/devices",
)
tasks_url = os.getenv(
    "TASKS_URL",
    "http://127.0.0.1:8080/api/v0/tasks",
)
jobs_url = os.getenv("JOBS_URL", "http://127.0.0.1:8080/api/v0/jobs")
milestones_url = os.getenv("MILESTONES_URL", "http://127.0.0.1:8080/api/v0/milestones")
staff_url = os.getenv("STAFF_URL", "http://127.0.0.1:8080/api/v0/staff")
process_plan_db_path = Path(os.getenv("PROCESS_PLAN_DB", Path(__file__).with_name("process_plans.sqlite3")))


@contextmanager
def plan_db():
    db = sqlite3.connect(process_plan_db_path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        db.execute("""CREATE TABLE IF NOT EXISTS local_milestones (
            id TEXT PRIMARY KEY, job_id INTEGER NOT NULL, title TEXT NOT NULL,
            company_id INTEGER
        )""")
        if "company_id" not in {row["name"] for row in db.execute("PRAGMA table_info(local_milestones)")}:
            db.execute("ALTER TABLE local_milestones ADD COLUMN company_id INTEGER")
        db.execute("""CREATE TABLE IF NOT EXISTS local_tasks (
            id TEXT PRIMARY KEY, job_id INTEGER NOT NULL, milestone_id TEXT NOT NULL,
            title TEXT NOT NULL, assignee INTEGER, assignee_name TEXT,
            date_due TEXT, status TEXT NOT NULL
        )""")
        db.execute("""CREATE TABLE IF NOT EXISTS local_task_links (
            task_id INTEGER PRIMARY KEY, job_id INTEGER NOT NULL,
            milestone_id TEXT NOT NULL, legacy_local_id TEXT UNIQUE
        )""")
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def local_plan_items(job_id):
    with plan_db() as db:
        milestones = [dict(row) for row in db.execute(
            "SELECT id, title FROM local_milestones WHERE job_id = ? ORDER BY rowid", (job_id,)
        )]
        tasks = [dict(row) for row in db.execute(
            """SELECT id, job_id, milestone_id, title, assignee, assignee_name, date_due, status
               FROM local_tasks WHERE job_id = ? ORDER BY rowid""", (job_id,)
        )]
    return milestones, tasks


def local_task_links(job_id):
    with plan_db() as db:
        return {row["task_id"]: row["milestone_id"] for row in db.execute(
            "SELECT task_id, milestone_id FROM local_task_links WHERE job_id = ?", (job_id,)
        )}


def numbered_task(task, job_id, milestone_id):
    try:
        task_id = int(task["id"])
    except (KeyError, TypeError, ValueError) as error:
        raise HTTPException(502, "Task API did not return a numeric ID") from error
    return {**task, "id": task_id, "job_id": job_id, "milestone_id": milestone_id}


def local_table_tasks(company_id, statuses, overdue, query, assignees=None):
    with plan_db() as db:
        rows = [dict(row) for row in db.execute(
            """SELECT t.id, t.job_id, t.milestone_id, t.title, t.assignee,
                      t.assignee_name, t.date_due, t.status, m.company_id
               FROM local_tasks AS t
               JOIN local_milestones AS m ON m.id = t.milestone_id
               ORDER BY t.rowid DESC"""
        )]
        job_companies = {}
        for task in rows:
            if task["company_id"] is None:
                job_id = task["job_id"]
                if job_id not in job_companies:
                    job_companies[job_id] = read_json(f"{jobs_url}/{job_id}")["response"]["company_id"]
                task["company_id"] = job_companies[job_id]
                db.execute(
                    "UPDATE local_milestones SET company_id = ? WHERE id = ?",
                    (task["company_id"], task["milestone_id"]),
                )

    today = date.today().isoformat()
    matches = []
    for task in rows:
        task["overdue"] = bool(task["date_due"] and task["date_due"] < today and task["status"] != "complete")
        if company_id is not None and task["company_id"] != company_id:
            continue
        if statuses and task["status"] not in statuses:
            continue
        if overdue is not None and task["overdue"] != overdue:
            continue
        if query and query not in task["title"].casefold():
            continue
        if assignees is not None and task_assignee(task) not in assignees:
            continue
        matches.append(task)
    return matches


def read_json(url):
    try:
        with urlopen(url, timeout=10) as upstream:
            return json.load(upstream)
    except HTTPError as error:
        raise HTTPException(error.code, error.read().decode(errors="replace")) from error
    except URLError as error:
        raise HTTPException(502, f"Could not reach API: {error.reason}") from error


def write_json(url, method, payload):
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    try:
        with urlopen(request, timeout=10) as upstream:
            return json.load(upstream)
    except HTTPError as error:
        raise HTTPException(error.code, error.read().decode(errors="replace")) from error
    except URLError as error:
        raise HTTPException(502, f"Could not reach API: {error.reason}") from error


def fetch_pages(url, limit, filters):
    items = []
    page = 0
    while True:
        query = urlencode({**filters, "_limit": limit, "_page": page})
        data = read_json(f"{url}?{query}")
        batch = data["response"]
        items.extend(batch)
        if not batch or len(items) >= data["meta"]["total"]:
            return items
        page += 1


def fetch_ncentral_pages(url, filters, page_size=50):
    items = []
    page = 1
    while True:
        query = urlencode({**filters, "pageNumber": page, "pageSize": page_size})
        data = read_json(f"{url}?{query}")
        batch = data["data"]
        items.extend(batch)
        if not batch or len(items) >= data["totalItems"] or page >= data["totalPages"]:
            return items
        page += 1


def count_accelo(url, limit, filters):
    query = urlencode({**filters, "_limit": limit, "_page": 0})
    return read_json(f"{url}?{query}")["meta"]["total"]


def count_ncentral(url, filters):
    query = urlencode({**filters, "pageNumber": 1, "pageSize": 50})
    return read_json(f"{url}?{query}")["totalItems"]


def selected_assignees(value):
    if not value:
        return None
    selected = set()
    for item in value.split(","):
        item = item.strip().lower()
        if item == "unassigned":
            selected.add(None)
        elif item.isdecimal():
            selected.add(int(item))
        else:
            raise HTTPException(422, "Invalid assignee")
    return selected


def task_assignee(item):
    value = item.get("assignee_id")
    if value is None:
        value = item.get("assignee")
    if isinstance(value, dict):
        value = value.get("id")
    if value in (None, "", 0, "0"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@app.get("/issues")
def issues():
    tickets = fetch_pages(issues_url, 100, {"status": "open"})
    return {"total": len(tickets), "issues": tickets}


def selected_statuses(value, order):
    if not value or value.lower() == "all":
        return []
    chosen = {item.strip().lower().replace(" ", "") for item in value.split(",")}
    if chosen - set(order):
        raise HTTPException(422, "Invalid status")
    return [item for item in order if item in chosen]


def due_date_key(item):
    value = item.get("date_due") or item.get("due_date")
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return date.max


def accelo_group_window(url, groups, offset, limit):
    if len(groups) == 1:
        filters = groups[0]
        first_page = offset // 10
        data = read_json(f"{url}?{urlencode({**filters, '_limit': 10, '_page': first_page})}")
        group_data = [(filters, data["meta"]["total"], first_page, data)]
    else:
        group_data = []
        for filters in groups:
            data = read_json(f"{url}?{urlencode({**filters, '_limit': 1, '_page': 0})}")
            group_data.append((filters, data["meta"]["total"], None, None))

    total = sum(count for _, count, _, _ in group_data)
    results = []
    for filters, count, cached_page, cached_data in group_data:
        if offset >= count:
            offset -= count
            continue
        while offset < count and len(results) < limit:
            page = offset // 10
            data = cached_data if page == cached_page else read_json(
                f"{url}?{urlencode({**filters, '_limit': 10, '_page': page})}"
            )
            batch = data["response"][offset % 10 : offset % 10 + limit - len(results)]
            if not batch:
                break
            results.extend(batch)
            offset += len(batch)
        offset = 0
        if len(results) == limit:
            break
    return total, results


@app.get("/tickets")
def tickets(
    page: int = 0,
    company_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    q: str | None = None,
    assignees: str | None = None,
):
    if page < 0:
        raise HTTPException(422, "page must be 0 or greater")

    filters = {}
    if company_id is not None:
        filters["company_id"] = company_id
    statuses = selected_statuses(status, ("open", "inprogress", "resolved", "closed"))
    if q and q.strip():
        filters["q"] = q.strip()

    priorities = {value.strip().lower() for value in priority.split(",")} if priority else set()
    priority_order = ("urgent", "high", "normal", "low")
    if priorities - set(priority_order):
        raise HTTPException(422, "Invalid priority")
    selected_priorities = [value for value in priority_order if value in priorities]
    assignee_ids = selected_assignees(assignees)

    if assignee_ids is not None:
        scan_filters = {key: value for key, value in filters.items() if key != "q"}
        if len(statuses) == 1:
            scan_filters["status"] = statuses[0]
        if len(selected_priorities) == 1:
            scan_filters["priority"] = selected_priorities[0]
        query = q.strip().casefold() if q and q.strip() else None
        matches = [
            ticket for ticket in fetch_pages(issues_url, 100, scan_filters)
            if task_assignee(ticket) in assignee_ids
            and (not statuses or str(ticket.get("status", "")).lower() in statuses)
            and (not selected_priorities or str(ticket.get("priority", "")).lower() in selected_priorities)
            and (not query or query in (ticket.get("title") or "").casefold()
                 or query in (ticket.get("description") or "").casefold())
        ]
        return {"page": page, "page_size": 10, "total": len(matches),
                "tickets": sorted(matches[page * 10 : (page + 1) * 10], key=due_date_key)}

    groups = [
        {**filters, **({"status": ticket_status} if ticket_status else {}),
         **({"priority": ticket_priority} if ticket_priority else {})}
        for ticket_status in (statuses or [None])
        for ticket_priority in (selected_priorities or [None])
    ]
    total, results = accelo_group_window(issues_url, groups, page * 10, 10)
    return {"page": page, "page_size": 10, "total": total, "tickets": sorted(results, key=due_date_key)}


@app.get("/tasks")
def tasks(
    page: int = 0,
    company_id: int | None = None,
    status: str | None = None,
    overdue: bool | None = None,
    q: str | None = None,
    assignees: str | None = None,
):
    if page < 0:
        raise HTTPException(422, "page must be 0 or greater")

    filters = {}
    if company_id is not None:
        filters["company_id"] = company_id
    statuses = selected_statuses(status, ("pending", "inprogress", "complete"))
    if overdue is not None:
        filters["overdue"] = str(overdue).lower()

    query = q.strip().casefold() if q and q.strip() else None
    assignee_ids = selected_assignees(assignees)
    local_matches = local_table_tasks(company_id, set(statuses), overdue, query, assignee_ids)
    offset = page * 10

    if query or assignee_ids is not None:
        scan_filters = {**filters, **({"status": statuses[0]} if len(statuses) == 1 else {})}
        remote_matches = [
            task for task in fetch_pages(tasks_url, 100, scan_filters)
            if (assignee_ids is None or task_assignee(task) in assignee_ids)
            and (not statuses or str(task.get("status", "")).lower() in statuses)
            and (not query or query in (task.get("title") or "").casefold()
                 or query in (task.get("description") or "").casefold())
        ]
        matches = local_matches + remote_matches
        return {"page": page, "page_size": 10, "total": len(matches),
                "tasks": sorted(matches[offset : offset + 10], key=due_date_key)}

    local_count = len(local_matches)
    page_tasks = local_matches[offset : offset + 10]
    remote_offset = max(0, offset - local_count)
    groups = [{**filters, **({"status": task_status} if task_status else {})} for task_status in (statuses or [None])]
    remote_total, remote_page = accelo_group_window(tasks_url, groups, remote_offset, 10 - len(page_tasks))
    page_tasks.extend(remote_page)
    return {"page": page, "page_size": 10, "total": local_count + remote_total,
            "tasks": sorted(page_tasks, key=due_date_key)}


@app.get("/companies")
def companies():
    items = fetch_pages(companies_url, 50, {})
    return sorted(
        ({"id": company["id"], "name": company["name"]} for company in items),
        key=lambda company: company["name"].casefold(),
    )


@app.get("/staff")
def staff():
    return {"staff": fetch_pages(staff_url, 100, {})}


class PlanTaskCreate(BaseModel):
    title: str = Field(min_length=1)
    milestone_id: int
    assignee: int | None = None
    date_due: date | None = None


class LocalMilestoneCreate(BaseModel):
    title: str = Field(min_length=1)


class LocalTaskCreate(BaseModel):
    title: str = Field(min_length=1)
    milestone_id: str
    assignee: int | None = None
    assignee_name: str | None = None
    date_due: date | None = None


class TaskCompletion(BaseModel):
    complete: bool


def plan_company_names():
    return {company["id"]: company["name"] for company in companies()}


@app.get("/process-plans")
def process_plans():
    names = plan_company_names()
    jobs = fetch_pages(jobs_url, 100, {})
    return {"plans": sorted(
        ({**job, "company_name": names.get(job["company_id"], "Unknown company")} for job in jobs),
        key=lambda job: (job["company_name"].casefold(), job["title"].casefold()),
    )}


@app.get("/process-plans/staff")
def process_plan_staff():
    return staff()


@app.get("/process-plans/{job_id}")
def process_plan(job_id: int):
    job = read_json(f"{jobs_url}/{job_id}")["response"]
    names = plan_company_names()
    milestones = fetch_pages(milestones_url, 100, {"job_id": job_id})
    tasks = fetch_pages(tasks_url, 100, {"job_id": job_id})
    local_milestones, local_tasks = local_plan_items(job_id)
    links = local_task_links(job_id)
    linked_ids = set()
    for index, task in enumerate(tasks):
        task_id = int(task["id"])
        if task_id in links:
            tasks[index] = {**task, "id": task_id, "milestone_id": links[task_id]}
            linked_ids.add(task_id)
    for task_id, milestone_id in links.items():
        if task_id not in linked_ids:
            try:
                task = read_json(f"{tasks_url}/{task_id}")["response"]
            except HTTPException as error:
                if error.status_code == 404:
                    continue
                raise
            tasks.append(numbered_task(task, job_id, milestone_id))
    milestones.extend(local_milestones)
    tasks.extend(local_tasks)
    completed = sum(task["status"] == "complete" for task in tasks)
    return {
        "job": {**job, "company_name": names.get(job["company_id"], "Unknown company")},
        "milestones": milestones,
        "tasks": tasks,
        "progress": {
            "completed": completed,
            "total": len(tasks),
            "percent": round(completed * 100 / len(tasks)) if tasks else 0,
        },
    }


@app.post("/process-plans/{job_id}/milestones")
def create_local_milestone(job_id: int, milestone: LocalMilestoneCreate):
    title = milestone.title.strip()
    if not title:
        raise HTTPException(422, "Milestone title is required")
    job = read_json(f"{jobs_url}/{job_id}")["response"]
    item = {"id": "local-milestone-" + uuid4().hex, "title": title}
    with plan_db() as db:
        db.execute(
            "INSERT INTO local_milestones (id, job_id, title, company_id) VALUES (?, ?, ?, ?)",
            (item["id"], job_id, title, job["company_id"]),
        )
    return item


@app.post("/process-plans/{job_id}/local-tasks")
def create_task_for_local_milestone(job_id: int, task: LocalTaskCreate):
    title = task.title.strip()
    if not title:
        raise HTTPException(422, "Task title is required")
    with plan_db() as db:
        milestone = db.execute(
            "SELECT id FROM local_milestones WHERE id = ? AND job_id = ?",
            (task.milestone_id, job_id),
        ).fetchone()
        if milestone is None:
            raise HTTPException(422, "Milestone does not belong to this plan")
    payload = {"title": title, "against_type": "job", "against_id": job_id}
    if task.assignee is not None:
        payload["assignee"] = task.assignee
    if task.date_due is not None:
        payload["date_due"] = task.date_due.isoformat()
    created = numbered_task(write_json(tasks_url, "POST", payload)["response"], job_id, task.milestone_id)
    with plan_db() as db:
        db.execute(
            "INSERT INTO local_task_links (task_id, job_id, milestone_id) VALUES (?, ?, ?)",
            (created["id"], job_id, task.milestone_id),
        )
    return {**created, "assignee_name": created.get("assignee_name") or task.assignee_name}


@app.post("/process-plans/{job_id}/local-tasks/{task_id}/sync")
def sync_local_task(job_id: int, task_id: str):
    with plan_db() as db:
        row = db.execute(
            "SELECT * FROM local_tasks WHERE id = ? AND job_id = ?", (task_id, job_id)
        ).fetchone()
        link = db.execute(
            "SELECT task_id, milestone_id FROM local_task_links WHERE legacy_local_id = ? AND job_id = ?",
            (task_id, job_id),
        ).fetchone()
    if row is None and link is None:
        raise HTTPException(404, "Task does not belong to this plan")
    if link is None:
        payload = {"title": row["title"], "against_type": "job", "against_id": job_id}
        if row["assignee"] is not None:
            payload["assignee"] = row["assignee"]
        if row["date_due"]:
            payload["date_due"] = row["date_due"]
        created = numbered_task(write_json(tasks_url, "POST", payload)["response"], job_id, row["milestone_id"])
        with plan_db() as db:
            db.execute(
                """INSERT INTO local_task_links (task_id, job_id, milestone_id, legacy_local_id)
                   VALUES (?, ?, ?, ?)""",
                (created["id"], job_id, row["milestone_id"], task_id),
            )
    else:
        created = numbered_task(
            read_json(f"{tasks_url}/{link['task_id']}")["response"], job_id, link["milestone_id"]
        )
    if row is not None:
        with plan_db() as db:
            db.execute("DELETE FROM local_tasks WHERE id = ? AND job_id = ?", (task_id, job_id))
        if row["status"] == "complete":
            write_json(f"{tasks_url}/{created['id']}", "PUT", {"complete": True})
    return created


@app.put("/process-plans/{job_id}/local-tasks/{task_id}")
def complete_local_task(job_id: int, task_id: str, update: TaskCompletion):
    with plan_db() as db:
        result = db.execute(
            "UPDATE local_tasks SET status = ? WHERE id = ? AND job_id = ?",
            ("complete" if update.complete else "pending", task_id, job_id),
        )
        if result.rowcount == 0:
            raise HTTPException(404, "Task does not belong to this plan")
        item = dict(db.execute(
            """SELECT id, job_id, milestone_id, title, assignee, assignee_name, date_due, status
               FROM local_tasks WHERE id = ?""", (task_id,)
        ).fetchone())
    return item


@app.post("/process-plans/{job_id}/tasks")
def create_process_plan_task(job_id: int, task: PlanTaskCreate):
    title = task.title.strip()
    if not title:
        raise HTTPException(422, "Task title is required")
    read_json(f"{jobs_url}/{job_id}")
    milestones = fetch_pages(milestones_url, 100, {"job_id": job_id})
    if not any(milestone["id"] == task.milestone_id for milestone in milestones):
        raise HTTPException(422, "Milestone does not belong to this plan")
    payload = {"title": title, "against_type": "milestone", "against_id": task.milestone_id}
    if task.assignee is not None:
        payload["assignee"] = task.assignee
    if task.date_due is not None:
        payload["date_due"] = task.date_due.isoformat()
    return write_json(tasks_url, "POST", payload)["response"]


@app.put("/process-plans/{job_id}/tasks/{task_id}")
def complete_process_plan_task(job_id: int, task_id: int, update: TaskCompletion):
    task = read_json(f"{tasks_url}/{task_id}")["response"]
    if task["job_id"] != job_id:
        raise HTTPException(404, "Task does not belong to this plan")
    payload = {"complete": True} if update.complete else {"status": "pending"}
    return write_json(f"{tasks_url}/{task_id}", "PUT", payload)["response"]


@app.get("/alerts")
def alerts():
    items = fetch_ncentral_pages(alerts_url, {"active": "true"})
    return {"total": len(items), "alerts": items}


@app.get("/alerts/page")
def alert_page(
    page: int = 0,
    active: bool | None = None,
    severity: str | None = None,
    q: str | None = None,
):
    if page < 0:
        raise HTTPException(422, "page must be 0 or greater")

    filters = {}
    if active is not None:
        filters["active"] = str(active).lower()
    if severity:
        severity = severity.lower().strip()
        if severity not in {"critical", "warning", "info"}:
            raise HTTPException(422, "Invalid severity")
        filters["severity"] = severity

    if q and q.strip():
        query = q.strip().casefold()
        matches = [
            alert for alert in fetch_ncentral_pages(alerts_url, filters, page_size=500)
            if any(query in str(alert.get(field) or "").casefold() for field in (
                "alertId", "message", "deviceName", "customerName", "serviceName"
            ))
        ]
        return {"page": page, "page_size": 10, "total": len(matches), "alerts": matches[page * 10 : (page + 1) * 10]}

    data = read_json(f"{alerts_url}?{urlencode({**filters, 'pageNumber': page + 1, 'pageSize': 10})}")
    return {"page": page, "page_size": 10, "total": data["totalItems"], "alerts": data["data"]}


@app.get("/offline-devices")
def offline_devices():
    items = fetch_ncentral_pages(devices_url, {"online": "false"})
    return {"total": len(items), "devices": items}


@app.get("/devices")
def devices(
    page: int = 0,
    device_class: str | None = None,
    online: bool | None = None,
    q: str | None = None,
):
    if page < 0:
        raise HTTPException(422, "page must be 0 or greater")

    filters = {"pageNumber": page + 1, "pageSize": 10}
    if device_class:
        device_class = device_class.lower().strip()
        if device_class not in {"workstation", "laptop", "server", "firewall", "switch", "printer"}:
            raise HTTPException(422, "Invalid device class")
        filters["device_class"] = device_class
    if online is not None:
        filters["online"] = str(online).lower()
    if q and q.strip():
        filters["q"] = q.strip()

    data = read_json(f"{devices_url}?{urlencode(filters)}")
    return {"page": page, "page_size": 10, "total": data["totalItems"], "devices": data["data"]}


@app.get("/overdue-tasks")
def overdue_tasks():
    items = fetch_pages(tasks_url, 50, {"overdue": "true"})
    return {"total": len(items), "tasks": items}


@app.get("/in-progress-tickets")
def in_progress_tickets():
    return {"total": count_accelo(issues_url, 100, {"status": "inprogress"})}


@app.get("/open-tickets")
def open_tickets():
    return {"total": count_accelo(issues_url, 100, {"status": "open"})}


@app.get("/high-priority-tickets")
def high_priority_tickets():
    return {"total": count_accelo(issues_url, 100, {"status": "open", "priority": "high"})}


@app.get("/urgent-tickets")
def urgent_tickets():
    return {"total": count_accelo(issues_url, 100, {"status": "open", "priority": "urgent"})}


@app.get("/new-tickets")
def new_tickets():
    return {"total": 0}


@app.get("/pending-tasks")
def pending_tasks():
    total = sum(
        count_accelo(tasks_url, 50, {"status": "pending", "overdue": overdue})
        for overdue in ("true", "false")
    )
    return {"total": total}


@app.get("/in-progress-tasks")
def in_progress_tasks():
    total = sum(
        count_accelo(tasks_url, 50, {"status": "inprogress", "overdue": overdue})
        for overdue in ("true", "false")
    )
    return {"total": total}


@app.get("/critical-alerts")
def critical_alerts():
    return {"total": count_ncentral(alerts_url, {"active": "true", "severity": "critical"})}


@app.get("/warning-alerts")
def warning_alerts():
    return {"total": count_ncentral(alerts_url, {"active": "true", "severity": "warning"})}


@app.get("/info-alerts")
def info_alerts():
    return {"total": count_ncentral(alerts_url, {"active": "true", "severity": "info"})}


@app.get("/online-devices")
def online_devices():
    return {"total": count_ncentral(devices_url, {"online": "true"})}



@app.get("/alerts-batched")
def alerts(page: int = 0, severity: str | None = None):

    if page < 0:
        raise HTTPException(422, "Invalid page")

    filters = {
        "active": "true",
        "pageNumber": page + 1,
        "pageSize": 10
    }

    if severity:
        severity = severity.lower().strip()
        if severity not in {"critical", "warning", "info"}:
            raise HTTPException(422, "Invalid severity")
        filters["severity"] = severity

    query = urlencode(filters)
    data = read_json(f"{alerts_url}?{query}")

    return {
        "page": page,
        "page_size": 10,
        "total": data["totalItems"],
        "alerts": data["data"]
    }
