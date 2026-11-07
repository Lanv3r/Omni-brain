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


def fetch_pages(url, limit, filters):
    items = []
    page = 0
    while True:
        query = urlencode({**filters, "_limit": limit, "_page": page})
        try:
            with urlopen(f"{url}?{query}", timeout=10) as upstream:
                data = json.load(upstream)
        except HTTPError as error:
            raise HTTPException(error.code, error.read().decode(errors="replace")) from error
        except URLError as error:
            raise HTTPException(502, f"Could not reach API: {error.reason}") from error
        batch = data["response"]
        items.extend(batch)
        if not batch or len(items) >= data["meta"]["total"]:
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
