from unittest.mock import MagicMock, patch

from app.config import ImapConfig
from app.imap_client import MailboxClient, ImapMessage


def test_new_messages_peeks_body_without_setting_seen_flag():
    config = ImapConfig(
        host="imap.example.com",
        port=993,
        ssl=True,
        username="user",
        password="password",
        mailbox="INBOX",
        spam_folder="Junk",
        poll_interval=30,
        connect_timeout=30,
    )
    mailbox_client = MailboxClient(config)

    mock_client = MagicMock()
    mock_client.search.return_value = [101]
    mock_client.fetch.return_value = {
        101: {b"SEQ": 1, b"BODY[]": b"From: test@example.com\r\nSubject: Test\r\n\r\nHello"}
    }
    mailbox_client.client = mock_client
    mailbox_client.uid_validity = 12345

    messages = list(mailbox_client.new_messages())

    assert len(messages) == 1
    assert messages[0] == ImapMessage(
        uid=101,
        uid_validity=12345,
        raw=b"From: test@example.com\r\nSubject: Test\r\n\r\nHello",
    )
    mock_client.fetch.assert_called_once_with([101], [b"BODY.PEEK[]"])
