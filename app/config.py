from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ImapConfig:
    host: str
    port: int
    ssl: bool
    username: str
    password: str
    mailbox: str
    spam_folder: str
    poll_interval: int
    connect_timeout: int


@dataclass(frozen=True)
class RspamdConfig:
    url: str
    password: str | None
    timeout: int


@dataclass(frozen=True)
class StateConfig:
    db_path: Path


@dataclass(frozen=True)
class Rule:
    name: str
    condition: str
    action: str
    target: str | None = None
    flag: str | None = None


@dataclass(frozen=True)
class Config:
    imap: ImapConfig
    rspamd: RspamdConfig
    state: StateConfig
    rules: tuple[Rule, ...]
    log_level: str
    web_port: int


def load_config(path: str | Path) -> Config:
    with Path(path).open(encoding="utf-8") as config_file:
        raw: dict[str, Any] = yaml.safe_load(config_file) or {}

    imap = raw["imap"]
    rspamd = raw["rspamd"]
    state = raw.get("state", {})
    logging = raw.get("logging", {})
    web = raw.get("web", {})
    rules = tuple(Rule(**rule) for rule in raw.get("rules", []))
    return Config(
        imap=ImapConfig(
            host=imap["host"], port=imap.get("port", 993), ssl=imap.get("ssl", True),
            username=os.environ.get("IMAP_USERNAME", imap["username"]),
            password=os.environ.get("IMAP_PASSWORD", imap["password"]),
            mailbox=imap.get("mailbox", "INBOX"), spam_folder=imap.get("spam_folder", "Junk"),
            poll_interval=imap.get("poll_interval", 30),
            connect_timeout=imap.get("connect_timeout", 30),
        ),
        rspamd=RspamdConfig(
            url=rspamd["url"].rstrip("/"),
            password=os.environ.get("RSPAMD_PASSWORD", rspamd.get("password")),
            timeout=rspamd.get("timeout", 30),
        ),
        state=StateConfig(db_path=Path(state.get("db_path", "/data/state.db"))),
        rules=rules,
        log_level=logging.get("level", "INFO").upper(),
        web_port=web.get("port", 8080),
    )
