import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:3000", "http://localhost:3000"],
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


def read_json(url):
    try:
        with urlopen(url, timeout=10) as upstream:
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


def fetch_ncentral_pages(url, filters):
    items = []
    page = 1
    while True:
        query = urlencode({**filters, "pageNumber": page, "pageSize": 50})
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


@app.get("/issues")
def issues():
    tickets = fetch_pages(issues_url, 100, {"status": "open"})
    return {"total": len(tickets), "issues": tickets}


def ticket_request(filters, limit, page):
    query = urlencode({**filters, "_limit": limit, "_page": page})
    return read_json(f"{issues_url}?{query}")


@app.get("/tickets")
def tickets(
    page: int = 0,
    company_id: int | None = None,
    status: str | None = None,
    priority: str | None = None,
    q: str | None = None,
):
    if page < 0:
        raise HTTPException(422, "page must be 0 or greater")

    filters = {}
    if company_id is not None:
        filters["company_id"] = company_id
    if status:
        status = status.lower().replace(" ", "")
        if status not in {"open", "inprogress", "resolved", "closed"}:
            raise HTTPException(422, "Invalid status")
        filters["status"] = status
    if q and q.strip():
        filters["q"] = q.strip()

    priorities = {value.strip().lower() for value in priority.split(",")} if priority else set()
    priority_order = ("urgent", "high", "normal", "low")
    if priorities - set(priority_order):
        raise HTTPException(422, "Invalid priority")
    selected_priorities = [value for value in priority_order if value in priorities]

    if len(selected_priorities) <= 1:
        if selected_priorities:
            filters["priority"] = selected_priorities[0]
        data = ticket_request(filters, 10, page)
        return {"page": page, "page_size": 10, "total": data["meta"]["total"], "tickets": data["response"]}

    groups = []
    for value in selected_priorities:
        group_filters = {**filters, "priority": value}
        total = ticket_request(group_filters, 1, 0)["meta"]["total"]
        groups.append((group_filters, total))

    total = sum(group_total for _, group_total in groups)
    offset = page * 10
    results = []
    for group_filters, group_total in groups:
        if offset >= group_total:
            offset -= group_total
            continue
        while offset < group_total and len(results) < 10:
            data = ticket_request(group_filters, 10, offset // 10)
            batch = data["response"][offset % 10 : offset % 10 + 10 - len(results)]
            if not batch:
                break
            results.extend(batch)
            offset += len(batch)
        offset = 0
        if len(results) == 10:
            break
    return {"page": page, "page_size": 10, "total": total, "tickets": results}


@app.get("/tasks")
def tasks(
    page: int = 0,
    company_id: int | None = None,
    status: str | None = None,
    overdue: bool | None = None,
    q: str | None = None,
):
    if page < 0:
        raise HTTPException(422, "page must be 0 or greater")

    filters = {}
    if company_id is not None:
        filters["company_id"] = company_id
    if status:
        status = status.lower().replace(" ", "")
        if status not in {"pending", "inprogress", "complete"}:
            raise HTTPException(422, "Invalid status")
        filters["status"] = status
    if overdue is not None:
        filters["overdue"] = str(overdue).lower()

    if q and q.strip():
        query = q.strip().casefold()
        matches = [
            task for task in fetch_pages(tasks_url, 100, filters)
            if query in (task.get("title") or "").casefold()
            or query in (task.get("description") or "").casefold()
        ]
        return {"page": page, "page_size": 10, "total": len(matches), "tasks": matches[page * 10 : (page + 1) * 10]}

    data = read_json(f"{tasks_url}?{urlencode({**filters, '_limit': 10, '_page': page})}")
    return {"page": page, "page_size": 10, "total": data["meta"]["total"], "tasks": data["response"]}


@app.get("/companies")
def companies():
    items = fetch_pages(companies_url, 50, {})
    return sorted(
        ({"id": company["id"], "name": company["name"]} for company in items),
        key=lambda company: company["name"].casefold(),
    )


@app.get("/alerts")
def alerts():
    items = fetch_ncentral_pages(alerts_url, {"active": "true"})
    return {"total": len(items), "alerts": items}


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
