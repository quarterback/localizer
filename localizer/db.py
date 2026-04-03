"""SQLite database layer for RFP storage and querying."""

import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

DEFAULT_DB_PATH = Path.home() / ".localizer" / "rfps.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS rfps (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    url TEXT,
    posted_date TEXT,
    due_date TEXT,
    category TEXT,
    estimated_value TEXT,
    contact_name TEXT,
    contact_email TEXT,
    status TEXT DEFAULT 'open',
    raw_html TEXT,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL,
    notified INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_rfps_source ON rfps(source);
CREATE INDEX IF NOT EXISTS idx_rfps_due_date ON rfps(due_date);
CREATE INDEX IF NOT EXISTS idx_rfps_status ON rfps(status);
CREATE INDEX IF NOT EXISTS idx_rfps_first_seen ON rfps(first_seen);
CREATE INDEX IF NOT EXISTS idx_rfps_notified ON rfps(notified);

CREATE TABLE IF NOT EXISTS scrape_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL,
    rfps_found INTEGER DEFAULT 0,
    rfps_new INTEGER DEFAULT 0,
    error TEXT
);
"""


@dataclass
class RFP:
    id: str
    source: str
    title: str
    description: Optional[str] = None
    url: Optional[str] = None
    posted_date: Optional[str] = None
    due_date: Optional[str] = None
    category: Optional[str] = None
    estimated_value: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    status: str = "open"
    raw_html: Optional[str] = None
    first_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_seen: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    notified: int = 0


class Database:
    def __init__(self, db_path: Path = DEFAULT_DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(db_path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def upsert_rfp(self, rfp: RFP) -> bool:
        """Insert or update an RFP. Returns True if this is a new RFP."""
        now = datetime.utcnow().isoformat()
        existing = self.conn.execute("SELECT id FROM rfps WHERE id = ?", (rfp.id,)).fetchone()

        if existing:
            self.conn.execute(
                """UPDATE rfps SET title=?, description=?, url=?, posted_date=?,
                   due_date=?, category=?, estimated_value=?, contact_name=?,
                   contact_email=?, status=?, raw_html=?, last_seen=?
                   WHERE id=?""",
                (
                    rfp.title, rfp.description, rfp.url, rfp.posted_date,
                    rfp.due_date, rfp.category, rfp.estimated_value, rfp.contact_name,
                    rfp.contact_email, rfp.status, rfp.raw_html, now, rfp.id,
                ),
            )
            self.conn.commit()
            return False
        else:
            rfp.first_seen = now
            rfp.last_seen = now
            d = asdict(rfp)
            cols = ", ".join(d.keys())
            placeholders = ", ".join(["?"] * len(d))
            self.conn.execute(f"INSERT INTO rfps ({cols}) VALUES ({placeholders})", list(d.values()))
            self.conn.commit()
            return True

    def get_new_rfps(self, since: Optional[str] = None) -> list[dict]:
        """Get RFPs first seen since the given ISO timestamp."""
        if since is None:
            since = datetime.utcnow().replace(hour=0, minute=0, second=0).isoformat()
        rows = self.conn.execute(
            "SELECT * FROM rfps WHERE first_seen >= ? ORDER BY first_seen DESC", (since,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_open_rfps(self, source: Optional[str] = None) -> list[dict]:
        """Get all open RFPs, optionally filtered by source."""
        if source:
            rows = self.conn.execute(
                "SELECT * FROM rfps WHERE status='open' AND source=? ORDER BY due_date ASC",
                (source,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM rfps WHERE status='open' ORDER BY due_date ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_unnotified_rfps(self) -> list[dict]:
        """Get RFPs that haven't been included in a notification yet."""
        rows = self.conn.execute(
            "SELECT * FROM rfps WHERE notified=0 ORDER BY first_seen DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def mark_notified(self, rfp_ids: list[str]):
        """Mark RFPs as notified."""
        self.conn.executemany(
            "UPDATE rfps SET notified=1 WHERE id=?", [(rid,) for rid in rfp_ids]
        )
        self.conn.commit()

    def log_scrape(self, source: str, status: str, rfps_found: int = 0,
                   rfps_new: int = 0, error: Optional[str] = None,
                   started_at: Optional[str] = None):
        now = datetime.utcnow().isoformat()
        self.conn.execute(
            """INSERT INTO scrape_log (source, started_at, finished_at, status, rfps_found, rfps_new, error)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (source, started_at or now, now, status, rfps_found, rfps_new, error),
        )
        self.conn.commit()

    def get_scrape_history(self, limit: int = 20) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM scrape_log ORDER BY finished_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]

    def search(self, query: str) -> list[dict]:
        """Full-text search across title and description."""
        pattern = f"%{query}%"
        rows = self.conn.execute(
            """SELECT * FROM rfps WHERE title LIKE ? OR description LIKE ?
               ORDER BY first_seen DESC""",
            (pattern, pattern),
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self):
        self.conn.close()
