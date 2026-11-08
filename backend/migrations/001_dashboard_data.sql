CREATE TABLE tickets (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    requester TEXT NOT NULL,
    company TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    assignee TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    company TEXT NOT NULL,
    status TEXT NOT NULL,
    due_date TEXT NOT NULL,
    assignee TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE alerts (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    severity TEXT NOT NULL,
    device TEXT NOT NULL,
    company TEXT NOT NULL,
    state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    display_order INTEGER NOT NULL
);

CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    operating_system TEXT NOT NULL,
    company TEXT NOT NULL,
    device_type TEXT NOT NULL,
    status TEXT NOT NULL,
    last_checkin TEXT NOT NULL,
    display_order INTEGER NOT NULL
);
