from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import Lock
from typing import Any

from .config import Rule


class ProcessingState:
    def __init__(self, database_path: Path) -> None:
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(database_path, check_same_thread=False)
        self.lock = Lock()
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS processed_messages (
                mailbox TEXT NOT NULL,
                uid_validity INTEGER NOT NULL,
                uid INTEGER NOT NULL,
                processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (mailbox, uid_validity, uid)
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                condition TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT,
                flag TEXT,
                enabled INTEGER NOT NULL DEFAULT 1
            )"""
        )
        self.connection.execute(
            """CREATE TABLE IF NOT EXISTS action_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                uid INTEGER NOT NULL,
                subject TEXT NOT NULL,
                sender TEXT NOT NULL,
                rspamd_score REAL NOT NULL,
                rspamd_action TEXT NOT NULL,
                rule_name TEXT NOT NULL,
                action TEXT NOT NULL,
                target TEXT
            )"""
        )
        self.connection.commit()

    def was_processed(self, mailbox: str, uid_validity: int, uid: int) -> bool:
        with self.lock:
            row = self.connection.execute(
                "SELECT 1 FROM processed_messages WHERE mailbox = ? AND uid_validity = ? AND uid = ?",
                (mailbox, uid_validity, uid),
            ).fetchone()
        return row is not None

    def mark_processed(self, mailbox: str, uid_validity: int, uid: int) -> None:
        with self.lock:
            self.connection.execute(
                "INSERT OR IGNORE INTO processed_messages (mailbox, uid_validity, uid) VALUES (?, ?, ?)",
                (mailbox, uid_validity, uid),
            )
            self.connection.commit()

    def reset_processed_messages(self) -> None:
        with self.lock:
            self.connection.execute("DELETE FROM processed_messages")
            self.connection.execute("DELETE FROM action_log")
            self.connection.commit()

    def seed_rules(self, rules: tuple[Rule, ...]) -> None:
        with self.lock:
            count = self.connection.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
            if count:
                return
            self.connection.executemany(
                "INSERT INTO rules (name, condition, action, target, flag) VALUES (?, ?, ?, ?, ?)",
                [(rule.name, rule.condition, rule.action, rule.target, rule.flag) for rule in rules],
            )
            self.connection.commit()

    def rules(self) -> tuple[Rule, ...]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT name, condition, action, target, flag FROM rules WHERE enabled = 1 ORDER BY id"
            ).fetchall()
        return tuple(Rule(*row) for row in rows)

    def list_rules(self) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                "SELECT id, name, condition, action, target, flag, enabled FROM rules ORDER BY id"
            ).fetchall()
        fields = ("id", "name", "condition", "action", "target", "flag", "enabled")
        return [dict(zip(fields, row)) for row in rows]

    def add_rule(self, rule: Rule) -> int:
        with self.lock:
            cursor = self.connection.execute(
                "INSERT INTO rules (name, condition, action, target, flag) VALUES (?, ?, ?, ?, ?)",
                (rule.name, rule.condition, rule.action, rule.target, rule.flag),
            )
            self.connection.execute("DELETE FROM processed_messages")
            self.connection.commit()
            return int(cursor.lastrowid)

    def delete_rule(self, rule_id: int) -> bool:
        with self.lock:
            cursor = self.connection.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
            if cursor.rowcount:
                self.connection.execute("DELETE FROM processed_messages")
            self.connection.commit()
            return cursor.rowcount > 0

    def log_action(
        self, uid: int, subject: str, sender: str, score: float, rspamd_action: str,
        rule_name: str, action: str, target: str | None,
    ) -> None:
        with self.lock:
            self.connection.execute(
                """INSERT INTO action_log
                   (uid, subject, sender, rspamd_score, rspamd_action, rule_name, action, target)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (uid, subject, sender, score, rspamd_action, rule_name, action, target),
            )
            self.connection.commit()

    def recent_actions(self, limit: int = 100) -> list[dict[str, Any]]:
        with self.lock:
            rows = self.connection.execute(
                """SELECT created_at, uid, subject, sender, rspamd_score, rspamd_action,
                   rule_name, action, target FROM action_log ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        fields = ("created_at", "uid", "subject", "sender", "rspamd_score", "rspamd_action", "rule_name", "action", "target")
        return [dict(zip(fields, row)) for row in rows]

    def close(self) -> None:
        with self.lock:
            self.connection.close()
