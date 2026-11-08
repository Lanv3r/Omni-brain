from fastapi import APIRouter
from pydantic import BaseModel

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
    company: str
    status: str
    due_date: str
    assignee: str
    display_order: int


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
