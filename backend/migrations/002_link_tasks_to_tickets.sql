ALTER TABLE tasks ADD COLUMN description TEXT NOT NULL DEFAULT '';
ALTER TABLE tasks ADD COLUMN ticket_id TEXT REFERENCES tickets(id) ON DELETE SET NULL;
ALTER TABLE tasks ADD COLUMN priority TEXT NOT NULL DEFAULT 'Medium';

CREATE INDEX tasks_ticket_id_idx ON tasks(ticket_id);
