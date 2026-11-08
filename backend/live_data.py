"""Read-only answers for current facts in the sandbox API."""

import json
import os
import re
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

ISSUES_URL = os.getenv("ISSUES_URL", "http://127.0.0.1:8080/api/v0/issues")
DEVICES_URL = os.getenv("DEVICES_URL", "http://127.0.0.1:8080/ncentral/devices")
COMPANIES_URL = os.getenv("COMPANIES_URL", "http://127.0.0.1:8080/api/v0/companies")
STAFF_URL = os.getenv("STAFF_URL", "http://127.0.0.1:8080/api/v0/staff")
JOBS_URL = os.getenv("JOBS_URL", "http://127.0.0.1:8080/api/v0/jobs")
TASKS_URL = os.getenv("TASKS_URL", "http://127.0.0.1:8080/api/v0/tasks")
ALERTS_URL = os.getenv("ALERTS_URL", "http://127.0.0.1:8080/ncentral/alerts")
PLAN_DB = Path(os.getenv("PROCESS_PLAN_DB", Path(__file__).with_name("process_plans.sqlite3")))
DEVICE_CLASSES = {
    "workstation": r"\bworkstations?\b",
    "laptop": r"\blaptops?\b",
    "server": r"\bservers?\b",
    "firewall": r"\bfirewalls?\b",
    "switch": r"\bswitch(?:es)?\b",
    "printer": r"\bprinters?\b",
}
TICKET_PRIORITIES = ("urgent", "high", "normal", "low")


class LiveDataError(Exception):
    """The sandbox could not supply a current answer."""


def read_page(url, params):
    try:
        with urlopen(f"{url}?{urlencode(params)}", timeout=10) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        raise LiveDataError("The sandbox API is unavailable right now.") from error


def accelo_pages(url, filters=None):
    items = []
    for page in range(1000):
        data = read_page(url, {**(filters or {}), "_limit": 100, "_page": page})
        try:
            batch = data["response"]
            total = int(data["meta"]["total"])
            if not isinstance(batch, list):
                raise TypeError("response is not a list")
        except (KeyError, TypeError, ValueError) as error:
            raise LiveDataError("The sandbox returned an unexpected Accelo response.") from error
        items.extend(batch)
        if not batch or len(items) >= total:
            return items
    raise LiveDataError("The sandbox returned too many Accelo pages.")


def ncentral_pages(url, filters=None):
    items = []
    for page in range(1, 1001):
        data = read_page(url, {**(filters or {}), "pageNumber": page, "pageSize": 50})
        try:
            batch = data["data"]
            total = int(data["totalItems"])
            if not isinstance(batch, list):
                raise TypeError("data is not a list")
        except (KeyError, TypeError, ValueError) as error:
            raise LiveDataError("The sandbox returned an unexpected N-central response.") from error
        items.extend(batch)
        if not batch or len(items) >= total:
            return items
    raise LiveDataError("The sandbox returned too many N-central pages.")


def unresolved_tickets():
    return accelo_pages(ISSUES_URL, {"status": "open"}) + accelo_pages(ISSUES_URL, {"status": "inprogress"})


def numbered_answer(intro, lines, total=None):
    if not lines:
        return intro
    answer = intro + "\n\n" + "\n".join(f"{index}. {line}" for index, line in enumerate(lines, 1))
    if total is not None and total > len(lines):
        answer += f"\n\nShowing {len(lines)} of {total}."
    return answer


def ticket_count(status, priority=None):
    filters = {"_limit": 1, "_page": 0}
    if status:
        filters["status"] = status
    if priority:
        filters["priority"] = priority
    try:
        return int(read_page(ISSUES_URL, filters)["meta"]["total"])
    except (KeyError, TypeError) as error:
        raise LiveDataError("The sandbox returned an unexpected ticket response.") from error


def offline_device_count(device_class):
    return sum(
        device_class is None or str(device.get("deviceClass", "")).casefold() == device_class
        for device in ncentral_pages(DEVICES_URL, {"online": "false"})
    )


def clients_with_unresolved_tickets():
    issues = unresolved_tickets()
    counts = Counter(str(issue["company_id"]) for issue in issues if issue.get("company_id") is not None)
    if not counts:
        return "No clients currently have open or in-progress tickets in the sandbox."
    names = {str(company["id"]): company["name"] for company in accelo_pages(COMPANIES_URL)}
    ranked = sorted(counts.items(), key=lambda item: (-item[1], names.get(item[0], item[0]).casefold()))
    lines = [f"{names.get(company_id, 'Company #' + company_id)} — {count} unresolved tickets"
             for company_id, count in ranked[:5]]
    return numbered_answer("Clients with the most unresolved tickets (open + in progress):", lines, len(ranked))


def technicians_with_assigned_tickets():
    issues = unresolved_tickets()
    counts = Counter()
    fallback_names = {}
    for issue in issues:
        assignee = issue.get("assignee")
        if isinstance(assignee, dict):
            assignee = assignee.get("id")
        if assignee in (None, "", 0, "0"):
            continue
        key = str(assignee)
        counts[key] += 1
        if issue.get("assignee_name"):
            fallback_names[key] = issue["assignee_name"]
    if not counts:
        return "No open or in-progress tickets are currently assigned to technicians in the sandbox."
    names = {str(member["id"]): member["name"] for member in accelo_pages(STAFF_URL)}
    ranked = sorted(counts.items(), key=lambda item: (-item[1], names.get(item[0], fallback_names.get(item[0], item[0])).casefold()))
    lines = [f"{names.get(staff_id, fallback_names.get(staff_id, 'Technician #' + staff_id))} — {count} tickets"
             for staff_id, count in ranked[:5]]
    return numbered_answer("Technicians with the most assigned open or in-progress tickets:", lines, len(ranked))


def devices_with_critical_alerts():
    alerts = [alert for alert in ncentral_pages(ALERTS_URL, {"active": "true", "severity": "critical"})
              if alert.get("active") is True and str(alert.get("severity", "")).casefold() == "critical"]
    if not alerts:
        return "No devices currently have active critical alerts in the sandbox."
    counts = Counter()
    labels = {}
    for alert in alerts:
        key = (str(alert.get("customerId") or alert.get("customerName") or ""),
               str(alert.get("deviceId") or alert.get("deviceName") or ""))
        counts[key] += 1
        labels[key] = (alert.get("deviceName") or f"Device #{key[1]}",
                       alert.get("customerName") or "Unknown client")
    ranked = sorted(counts.items(), key=lambda item: (-item[1], labels[item[0]][1].casefold(), labels[item[0]][0].casefold()))
    lines = [f"{labels[key][0]} ({labels[key][1]}) — {count} critical alert{'s' if count != 1 else ''}"
             for key, count in ranked[:10]]
    return numbered_answer(f"{len(ranked)} devices currently have active critical alerts:", lines, len(ranked))


def saved_overdue_onboarding_tasks(today, job_ids):
    if not PLAN_DB.exists():
        return []
    try:
        with closing(sqlite3.connect(f"file:{PLAN_DB}?mode=ro", uri=True)) as db:
            db.row_factory = sqlite3.Row
            rows = [dict(row) for row in db.execute(
                """SELECT t.title, t.date_due, p.title AS plan_title, p.company_name
                   FROM local_plan_tasks AS t JOIN local_plans AS p ON p.id = t.plan_id
                   WHERE lower(p.title) LIKE '%onboard%' AND t.date_due < ? AND t.status != 'complete'""",
                (today,),
            )]
            if job_ids:
                rows.extend(dict(row) for row in db.execute(
                    """SELECT t.title, t.date_due, t.job_id
                       FROM local_tasks AS t
                       WHERE t.date_due < ? AND t.status != 'complete'""", (today,)
                ) if str(row["job_id"]) in job_ids)
            return rows
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return []
        raise LiveDataError("Saved process plans could not be read.") from error


def overdue_onboarding_tasks():
    jobs = {str(job["id"]): job for job in accelo_pages(JOBS_URL)
            if re.search(r"\bonboard", str(job.get("title", "")), re.IGNORECASE)}
    today = date.today().isoformat()
    remote = [task for task in accelo_pages(TASKS_URL, {"overdue": "true"})
              if str(task.get("job_id")) in jobs and task.get("status") != "complete"]
    local = saved_overdue_onboarding_tasks(today, set(jobs))
    if not remote and not local:
        return "No. There are no overdue tasks under onboarding jobs or saved plans right now."
    names = {str(company["id"]): company["name"] for company in accelo_pages(COMPANIES_URL)} if remote or local else {}
    items = [
        (task.get("date_due") or "", task.get("title") or "Untitled task",
         jobs[str(task["job_id"])].get("title") or "Onboarding job",
         names.get(str(task.get("company_id")), "Unknown client"))
        for task in remote
    ]
    for task in local:
        job = jobs.get(str(task.get("job_id")))
        items.append((task.get("date_due") or "", task["title"],
                      task.get("plan_title") or (job.get("title") if job else "Onboarding plan"),
                      task.get("company_name") or (names.get(str(job.get("company_id"))) if job else "Unknown client")))
    items.sort(key=lambda item: (item[0], item[3], item[1]))
    lines = [f"{title} — {client}; {plan}; due {due}" for due, title, plan, client in items[:10]]
    return numbered_answer(f"Yes. There are {len(items)} overdue onboarding tasks:", lines, len(items))


def devices_with_expired_warranties():
    today = date.today().isoformat()
    expired = []
    for device in ncentral_pages(DEVICES_URL):
        expiry = str(device.get("warrantyExpiry") or "")[:10]
        if (expiry < today if expiry else device.get("warrantyExpired") is True):
            expired.append((expiry, device))
    if not expired:
        return f"No N-central devices have expired warranties as of {today}."
    expired.sort(key=lambda item: (item[0] or "9999-12-31", str(item[1].get("customerName", "")),
                                   str(item[1].get("hostname", ""))))
    lines = []
    for expiry, device in expired[:10]:
        name = device.get("hostname") or device.get("longName") or f"Device #{device.get('deviceId')}"
        client = device.get("customerName") or "Unknown client"
        lines.append(f"{name} ({client}) — expired {expiry or 'date unavailable'}")
    return numbered_answer(f"{len(expired)} N-central devices have expired warranties as of {today}:",
                           lines, len(expired))


def answer_live_question(question):
    """Return an answer for supported live queries, or None for document RAG."""
    text = question.casefold()
    asks_count = bool(re.search(r"\b(how many|count|number of|total|any|are there)\b", text))
    mentions_tickets = bool(re.search(r"\b(tickets?|issues?)\b", text))

    if (mentions_tickets and re.search(r"\b(clients?|companies|customers?)\b", text)
            and re.search(r"\b(most|top|highest)\b", text)
            and re.search(r"\b(unresolved|open|in[ -]?progress)\b", text)):
        return clients_with_unresolved_tickets()

    if (mentions_tickets and re.search(r"\b(technicians?|staff|employees?)\b", text)
            and re.search(r"\b(most|top|highest)\b", text)):
        return technicians_with_assigned_tickets()

    if (re.search(r"\bdevices?\b", text) and re.search(r"\balerts?\b", text)
            and re.search(r"\bactive\b", text) and re.search(r"\bcritical\b", text)):
        return devices_with_critical_alerts()

    if (re.search(r"\btasks?\b", text) and re.search(r"\boverdue\b", text)
            and re.search(r"\bonboard(?:ing)?\b", text)):
        return overdue_onboarding_tasks()

    if (re.search(r"\bdevices?\b", text) and re.search(r"\bwarrant(?:y|ies)\b", text)
            and re.search(r"\bexpired?\b", text)):
        return devices_with_expired_warranties()

    if mentions_tickets and (asks_count or "critical" in text):
        status = next((value for pattern, value in (
            (r"\bin[ -]?progress\b", "inprogress"),
            (r"\bresolved\b", "resolved"),
            (r"\bclosed\b", "closed"),
            (r"\bopen\b", "open"),
        ) if re.search(pattern, text)), None)
        if re.search(r"\bcritical\b", text):
            urgent = ticket_count(status or "open", "urgent")
            scope = status or "open"
            return ("The sandbox has no 'critical' ticket priority; it uses urgent, high, normal, and low. "
                    f"If you mean urgent, there are {urgent} {scope} urgent tickets right now.")
        priority = next((value for value in TICKET_PRIORITIES if re.search(rf"\b{value}\b", text)), None)
        count = ticket_count(status, priority)
        description = " ".join(part for part in (status or "all", priority, "tickets") if part)
        return f"The sandbox currently has {count} {description}."

    device_class = next((value for value, pattern in DEVICE_CLASSES.items() if re.search(pattern, text)), None)
    asks_offline = bool(re.search(r"\boffline\b", text))
    is_device_question = bool(device_class or re.search(r"\bdevices?\b", text))
    if asks_offline and is_device_question and (asks_count or device_class):
        count = offline_device_count(device_class)
        label = ("switches" if device_class == "switch" else f"{device_class}s") if device_class else "devices"
        if re.search(r"\b(any|are there)\b", text):
            return f"{'Yes' if count else 'No'}. The sandbox currently has {count} offline {label}."
        return f"The sandbox currently has {count} offline {label}."

    return None
