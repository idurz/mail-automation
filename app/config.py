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
    host = _environment_or_config("IMAP_HOST", imap.get("host"))
    username = _environment_or_config("IMAP_USERNAME", imap.get("username"))
    password = _environment_or_config("IMAP_PASSWORD", imap.get("password"))
    port = _imap_port(_environment_or_config("IMAP_PORT", imap.get("port", 993)))
    if not host:
        raise ValueError("IMAP host is required: set IMAP_HOST or imap.host")
    if not username:
        raise ValueError("IMAP username is required: set IMAP_USERNAME or imap.username")
    if not password:
        raise ValueError("IMAP password is required: set IMAP_PASSWORD or imap.password")
    rspamd = raw["rspamd"]
    state = raw.get("state", {})
    logging = raw.get("logging", {})
    web = raw.get("web", {})
    rules = tuple(Rule(**rule) for rule in raw.get("rules", []))
    return Config(
        imap=ImapConfig(
            host=host,
            port=port,
            ssl=imap.get("ssl", True),
            username=username,
            password=password,
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


def _environment_or_config(name: str, fallback: Any) -> Any:
    value = os.environ.get(name)
    return value if value else fallback


def _imap_port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("IMAP port must be a number: set IMAP_PORT or imap.port") from error
    if not 1 <= port <= 65535:
        raise ValueError("IMAP port must be between 1 and 65535")
    return port
