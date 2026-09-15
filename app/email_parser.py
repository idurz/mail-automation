from __future__ import annotations

from dataclasses import dataclass
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    content: bytes


@dataclass(frozen=True)
class ParsedEmail:
    subject: str
    from_addr: str
    from_name: str
    to_addr: str
    message_id: str
    text: str
    size: int
    attachments: tuple[Attachment, ...] = ()


def parse_email(raw_message: bytes) -> ParsedEmail:
    message: EmailMessage = BytesParser(policy=policy.default).parsebytes(raw_message)
    from_name, from_addr = parseaddr(str(message.get("From", "")))
    return ParsedEmail(
        subject=str(message.get("Subject", "")),
        from_addr=from_addr,
        from_name=from_name,
        to_addr=parseaddr(str(message.get("To", "")))[1],
        message_id=str(message.get("Message-ID", "")),
        text=_plain_text(message),
        size=len(raw_message),
        attachments=_attachments(message),
    )


def _plain_text(message: EmailMessage) -> str:
    parts = message.walk() if message.is_multipart() else (message,)
    return "\n".join(
        part.get_content()
        for part in parts
        if part.get_content_type() == "text/plain" and not part.get_content_disposition()
    )


def _attachments(message: EmailMessage) -> tuple[Attachment, ...]:
    if not message.is_multipart():
        return ()
    attachments = []
    for part in message.walk():
        if part.get_content_disposition() != "attachment":
            continue
        content = part.get_content()
        if isinstance(content, str):
            content = content.encode("utf-8")
        attachments.append(Attachment(
            filename=part.get_filename() or "attachment",
            content_type=part.get_content_type(),
            content=content,
        ))
    return tuple(attachments)
