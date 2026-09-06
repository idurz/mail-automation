from __future__ import annotations

from dataclasses import dataclass
import json
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
    imap_accounts: tuple[ImapConfig, ...]
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
        imap_accounts=_imap_accounts(imap),
        rspamd=RspamdConfig(
            url=_environment_or_config("RSPAMD_URL", rspamd["url"]).rstrip("/"),
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


def _imap_accounts(defaults: dict[str, Any]) -> tuple[ImapConfig, ...]:
    encoded_accounts = os.environ.get("IMAP_ACCOUNTS")
    if encoded_accounts:
        try:
            accounts = json.loads(encoded_accounts)
        except json.JSONDecodeError as error:
            raise ValueError("IMAP_ACCOUNTS must be a JSON list of account objects") from error
        if not isinstance(accounts, list) or not accounts or not all(isinstance(account, dict) for account in accounts):
            raise ValueError("IMAP_ACCOUNTS must be a non-empty JSON list of account objects")
        return tuple(_imap_config(account, defaults) for account in accounts)
    return (_imap_config({
        "host": _environment_or_config("IMAP_HOST", defaults.get("host")),
        "port": _environment_or_config("IMAP_PORT", defaults.get("port", 993)),
        "username": _environment_or_config("IMAP_USERNAME", defaults.get("username")),
        "password": _environment_or_config("IMAP_PASSWORD", defaults.get("password")),
    }, defaults),)


def _imap_config(account: dict[str, Any], defaults: dict[str, Any]) -> ImapConfig:
    host = account.get("host")
    username = account.get("username")
    password = account.get("password")
    if not host:
        raise ValueError("each IMAP account requires host")
    if not username:
        raise ValueError("each IMAP account requires username")
    if not password:
        raise ValueError("each IMAP account requires password")
    return ImapConfig(
        host=str(host),
        port=_imap_port(account.get("port", defaults.get("port", 993))),
        ssl=bool(account.get("ssl", defaults.get("ssl", True))),
        username=str(username),
        password=str(password),
        mailbox=str(account.get("mailbox", defaults.get("mailbox", "INBOX"))),
        spam_folder=str(account.get("spam_folder", defaults.get("spam_folder", "Junk"))),
        poll_interval=int(account.get("poll_interval", defaults.get("poll_interval", 30))),
        connect_timeout=int(account.get("connect_timeout", defaults.get("connect_timeout", 30))),
    )


def _imap_port(value: Any) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("IMAP port must be a number: set IMAP_PORT or imap.port") from error
    if not 1 <= port <= 65535:
        raise ValueError("IMAP port must be between 1 and 65535")
    return port
