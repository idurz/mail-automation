from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
import imaplib
import ssl

from imapclient import IMAPClient

from .config import ImapConfig


@dataclass(frozen=True)
class ImapMessage:
    uid: int
    uid_validity: int
    raw: bytes


class MailboxClient:
    def __init__(self, config: ImapConfig) -> None:
        self.config = config
        self.client: IMAPClient | None = None
        self.uid_validity: int | None = None

    def connect(self) -> None:
        ssl_context = ssl.create_default_context() if self.config.ssl else None
        self.client = IMAPClient(
            self.config.host,
            port=self.config.port,
            ssl=self.config.ssl,
            ssl_context=ssl_context,
            timeout=self.config.connect_timeout,
        )
        self.client.login(self.config.username, self.config.password)
        response = self.client.select_folder(self.config.mailbox, readonly=False)
        self.uid_validity = int(response[b"UIDVALIDITY"])

    def new_messages(self) -> Iterator[ImapMessage]:
        client, uid_validity = self._connected()
        for uid in client.search(["ALL"]):
            fetched = client.fetch([uid], [b"RFC822"])
            raw = fetched[uid][b"RFC822"]
            yield ImapMessage(uid=uid, uid_validity=uid_validity, raw=raw)

    def execute_action(self, uid: int, action: str, target: str | None, flag: str | None) -> None:
        client, _ = self._connected()
        if action == "none":
            return
        if action == "flag":
            client.add_flags([uid], [flag or "\\Flagged"])
        elif action == "move":
            if not target:
                raise ValueError("move action requires target")
            client.move([uid], target)
        elif action == "copy":
            if not target:
                raise ValueError("copy action requires target")
            client.copy([uid], target)
        elif action == "delete":
            client.delete_messages([uid])
            client.expunge()
        else:
            raise ValueError(f"unsupported action: {action}")

    def close(self) -> None:
        if self.client is not None:
            try:
                self.client.logout()
            except (OSError, imaplib.IMAP4.abort):
                pass
            finally:
                self.client = None
                self.uid_validity = None

    def _connected(self) -> tuple[IMAPClient, int]:
        if self.client is None or self.uid_validity is None:
            raise RuntimeError("IMAP client is not connected")
        return self.client, self.uid_validity
