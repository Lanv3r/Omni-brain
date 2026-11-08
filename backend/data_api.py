from datetime import date
from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter
from fastapi import HTTPException
from pydantic import BaseModel, Field

from backend.database import dashboard_summary, database_connection, list_records


router = APIRouter(prefix="/api/v1")


class TicketRecord(BaseModel):
    id: str
    subject: str
    requester: str
    company: str
    status: str
    priority: str
    assignee: str
    updated_at: str
    display_order: int


class TaskRecord(BaseModel):
    id: str
    title: str
    description: str
    company: str
    status: str
    priority: str
    due_date: str
    assignee: str
    display_order: int
    ticket_id: Optional[str] = None


class CreateTask(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(default="", max_length=4000)
    due_date: date
    assignee: Literal[
        "Unassigned",
        "Morgan Chen",
        "Taylor Brooks",
        "Jamie Park",
        "Alex Morgan",
        "Sam Rivera",
    ] = "Unassigned"
    priority: Literal["Urgent", "High", "Medium", "Low"] = "Medium"


class AlertRecord(BaseModel):
    id: str
    title: str
    severity: str
    device: str
    company: str
    state: str
    created_at: str
    display_order: int


class DeviceRecord(BaseModel):
    id: str
    operating_system: str
    company: str
    device_type: str
    status: str
    last_checkin: str
    display_order: int


class DashboardSummary(BaseModel):
    tickets: int
    tasks: int
    alerts: int
    devices: int


@router.get("/tickets", response_model=list[TicketRecord])
def get_tickets():
    return list_records("tickets")


@router.get("/tasks", response_model=list[TaskRecord])
def get_tasks():
    return list_records("tasks")


@router.get("/tickets/{ticket_id}/tasks", response_model=list[TaskRecord])
def get_ticket_tasks(ticket_id: str):
    with database_connection() as connection:
        ticket = connection.execute(
            "SELECT id FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        rows = connection.execute(
            "SELECT * FROM tasks WHERE ticket_id = ? ORDER BY display_order, id",
            (ticket_id,),
        ).fetchall()
    return [dict(row) for row in rows]


@router.post(
    "/tickets/{ticket_id}/tasks",
    response_model=TaskRecord,
    status_code=201,
)
def create_ticket_task(ticket_id: str, request: CreateTask):
    title = request.title.strip()
    assignee = request.assignee.strip() or "Unassigned"
    if not title:
        raise HTTPException(status_code=422, detail="Enter a task title.")

    with database_connection() as connection:
        ticket = connection.execute(
            "SELECT company FROM tickets WHERE id = ?", (ticket_id,)
        ).fetchone()
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        display_order = connection.execute(
            "SELECT COALESCE(MAX(display_order), 0) + 1 FROM tasks"
        ).fetchone()[0]
        task_id = f"TASK-{uuid4().hex[:8].upper()}"
        connection.execute(
            """
            INSERT INTO tasks
                (id, title, description, company, status, due_date, assignee,
                 display_order, ticket_id, priority)
            VALUES (?, ?, ?, ?, 'Pending', ?, ?, ?, ?, ?)
            """,
            (
                task_id,
                title,
                request.description.strip(),
                ticket["company"],
                request.due_date.isoformat(),
                assignee,
                display_order,
                ticket_id,
                request.priority,
            ),
        )
        connection.commit()
        row = connection.execute(
            "SELECT * FROM tasks WHERE id = ?", (task_id,)
        ).fetchone()
    return dict(row)


@router.get("/alerts", response_model=list[AlertRecord])
def get_alerts():
    return list_records("alerts")


@router.get("/devices", response_model=list[DeviceRecord])
def get_devices():
    return list_records("devices")


@router.get("/summary", response_model=DashboardSummary)
def get_summary():
    return dashboard_summary()


@router.get("/health")
def get_database_health():
    with database_connection() as connection:
        connection.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "ok"}
