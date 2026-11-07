import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["http://127.0.0.1:3000"])
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


@app.get("/issues")
def issues():
    tickets = fetch_pages(issues_url, 100, {"status": "open"})
    return {"total": len(tickets), "issues": tickets}


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


@app.get("/overdue-tasks")
def overdue_tasks():
    items = fetch_pages(tasks_url, 50, {"overdue": "true"})
    return {"total": len(items), "tasks": items}
