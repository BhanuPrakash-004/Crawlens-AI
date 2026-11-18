"""Durable single-instance audit storage. Connections are short lived and thread safe."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from backend.app.schemas import AuditJob


class AuditStore:
    def __init__(self, path: str):
        self.path = str(Path(path).resolve())
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS audits (id TEXT PRIMARY KEY, website TEXT NOT NULL, created_at TEXT NOT NULL, status TEXT NOT NULL, score INTEGER, pages INTEGER, issues INTEGER, payload TEXT NOT NULL)')
            db.execute('CREATE INDEX IF NOT EXISTS audits_created ON audits(created_at DESC)')
            db.execute('PRAGMA user_version=1')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def save(self, job: AuditJob):
        report = job.report
        with self.connect() as db:
            db.execute('INSERT INTO audits VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET status=excluded.status, score=excluded.score, pages=excluded.pages, issues=excluded.issues, payload=excluded.payload',
                       (job.audit_id, job.website, job.created_at, job.status, report.overall_score if report else None, report.pages_crawled if report else None, len(report.issues) if report else None, job.model_dump_json()))

    def get(self, audit_id: str):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM audits WHERE id=?', (audit_id,)).fetchone()
        return AuditJob.model_validate_json(row['payload']) if row else None

    def list(self, query: str = '', limit: int = 20, offset: int = 0):
        # instr treats %, _ and quotes literally; all inputs remain bound parameters.
        with self.connect() as db:
            total = db.execute('SELECT COUNT(*) FROM audits WHERE instr(lower(website),lower(?))>0', (query,)).fetchone()[0]
            rows = db.execute('SELECT id AS audit_id,website,created_at,status,score,pages,issues FROM audits WHERE instr(lower(website),lower(?))>0 ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?', (query,limit,offset)).fetchall()
        return {'items': [dict(row) for row in rows], 'total': total, 'limit': limit, 'offset': offset}

    def recover_interrupted(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM audits WHERE status IN ('queued','running')").fetchall()
        for row in rows:
            job = AuditJob.model_validate_json(row['payload'])
            job.status, job.stage = 'failed', 'interrupted'
            job.error = 'The server stopped before this audit finished. Start a new audit; any saved evidence is retained.'
            self.save(job)
