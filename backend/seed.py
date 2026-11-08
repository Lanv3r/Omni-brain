from __future__ import annotations

from pathlib import Path

from backend.database import database_connection, initialize_database


DEMO_TICKETS = [
    ("DEMO-1048", "New starter can't access email", "Jordan Lee", "Brightside Studio", "New", "High", "Morgan Chen", "18 min ago", 1),
    ("DEMO-1047", "VPN disconnects during calls", "Sam Rivera", "Harbor & Pine", "In progress", "Medium", "Taylor Brooks", "46 min ago", 2),
    ("DEMO-1046", "Request for a shared project folder", "Casey Patel", "Cedar Works", "Resolved", "Low", "Unassigned", "2 hr ago", 3),
    ("DEMO-1045", "Laptop running out of disk space", "Alex Morgan", "Northstar Design", "New", "Medium", "Jamie Park", "3 hr ago", 4),
    ("DEMO-1044", "Unable to print from finance workstation", "Riley Thompson", "Willow Accounting", "In progress", "Urgent", "Morgan Chen", "Yesterday", 5),
]

DEMO_TASKS = [
    ("DEMO-T312", "Review failed nightly backup", "Brightside Studio", "Overdue", "2026-11-05", "Morgan Chen", 1),
    ("DEMO-T311", "Replace finance workstation", "Willow Accounting", "Overdue", "2026-11-06", "Jamie Park", 2),
    ("DEMO-T310", "Restore shared folder permissions", "Cedar Works", "Overdue", "2026-11-06", "Taylor Brooks", 3),
    ("DEMO-T309", "Prepare new employee laptop", "Northstar Design", "Pending", "2026-11-08", "Alex Morgan", 4),
    ("DEMO-T308", "Schedule network maintenance", "Harbor & Pine", "Pending", "2026-11-09", "Sam Rivera", 5),
    ("DEMO-T307", "Configure secure remote access", "Willow Accounting", "In progress", "2026-11-10", "Morgan Chen", 6),
    ("DEMO-T306", "Apply workstation security updates", "Brightside Studio", "In progress", "2026-11-11", "Jamie Park", 7),
]

DEMO_ALERTS = [
    ("DEMO-A203", "Server not responding", "Critical", "HQ-FILE-01", "Brightside Studio", "Active", "4 min ago", 1),
    ("DEMO-A202", "Backup job failed", "Critical", "BACKUP-02", "Willow Accounting", "Active", "12 min ago", 2),
    ("DEMO-A201", "Disk space below 15%", "Warning", "DESIGN-WS-14", "Northstar Design", "Active", "19 min ago", 3),
    ("DEMO-A200", "Endpoint protection needs attention", "Warning", "CEDAR-LT-08", "Cedar Works", "Active", "31 min ago", 4),
    ("DEMO-A199", "Device has pending updates", "Warning", "HARBOR-WS-03", "Harbor & Pine", "Active", "52 min ago", 5),
    ("DEMO-A198", "Scheduled maintenance completed", "Info", "WILLOW-SQL-01", "Willow Accounting", "Active", "1 hr ago", 6),
]

DEMO_DEVICES = [
    ("BRIGHT-HQ-01", "Windows Server 2022", "Brightside Studio", "Server", "Online", "2 min ago", 1),
    ("WILLOW-WS-07", "Windows 11 Pro", "Willow Accounting", "Workstation", "Offline", "43 min ago", 2),
    ("NORTHSTAR-NAS-01", "Synology DSM", "Northstar Design", "Storage", "Online", "4 min ago", 3),
    ("HARBOR-FW-01", "FortiGate 80F", "Harbor & Pine", "Firewall", "Online", "1 min ago", 4),
    ("CEDAR-LT-08", "Windows 11 Pro", "Cedar Works", "Laptop", "Offline", "1 hr ago", 5),
    ("WILLOW-SQL-01", "Windows Server 2022", "Willow Accounting", "Server", "Online", "3 min ago", 6),
    ("BRIGHT-WS-14", "Windows 11 Pro", "Brightside Studio", "Workstation", "Online", "5 min ago", 7),
]


def seed_demo_data(database_path: str | Path | None = None) -> None:
    initialize_database(database_path)
    with database_connection(database_path) as connection:
        connection.executemany(
            """
            INSERT OR IGNORE INTO tickets
                (id, subject, requester, company, status, priority, assignee, updated_at, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            DEMO_TICKETS,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO tasks
                (id, title, company, status, due_date, assignee, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            DEMO_TASKS,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO alerts
                (id, title, severity, device, company, state, created_at, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            DEMO_ALERTS,
        )
        connection.executemany(
            """
            INSERT OR IGNORE INTO devices
                (id, operating_system, company, device_type, status, last_checkin, display_order)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            DEMO_DEVICES,
        )
        connection.commit()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
    seed_demo_data()
    print("Demo records are ready in the configured SQLite database.")
