from __future__ import annotations

import argparse
from datetime import datetime, timezone
import logging
from logging.handlers import RotatingFileHandler
import signal
import time

from .config import load_config
from .config import ImapConfig
from .email_parser import ParsedEmail, parse_email
from .imap_client import MailboxClient
from .paperless import PaperlessClient
from .rspamd import RspamdClient
from .rules import RuleError, RuleEvaluator
from .state import ProcessingState
from .web import start_server

LOGGER = logging.getLogger(__name__)
RUNNING = True


def stop(*_args: object) -> None:
    global RUNNING
    RUNNING = False


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(), RotatingFileHandler("/data/app.log", maxBytes=5_242_880, backupCount=3)],
    )


def run(config_path: str) -> None:
    config = load_config(config_path)
    configure_logging(config.log_level)
    LOGGER.info(f"Loaded configuration from {config_path}")
    for imap_config in config.imap_accounts:
        LOGGER.info("IMAP host: %s:%s mailbox: %s", imap_config.host, imap_config.port, imap_config.mailbox)

    state = ProcessingState(config.state.db_path)
    state.seed_rules(config.rules)
    start_server(state, config.web_port)
    rspamd = RspamdClient(config.rspamd)
    paperless = PaperlessClient(config.paperless) if config.paperless else None
    evaluator = RuleEvaluator()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while RUNNING:
            for imap_config in config.imap_accounts:
                if RUNNING:
                    _process_mailbox(imap_config, state, rspamd, evaluator, paperless)
            if RUNNING:
                time.sleep(min(account.poll_interval for account in config.imap_accounts))
    finally:
        state.close()


def _process_mailbox(
    imap_config: ImapConfig, state: ProcessingState, rspamd: RspamdClient, evaluator: RuleEvaluator,
    paperless: PaperlessClient | None,
) -> None:
    mailbox = MailboxClient(imap_config)
    mailbox_key = f"{imap_config.username}@{imap_config.host}/{imap_config.mailbox}"
    try:
        mailbox.connect()
        LOGGER.info("connected to %s mailbox %s", imap_config.host, imap_config.mailbox)
        now = datetime.now(timezone.utc)
        for item in mailbox.new_messages():
            if state.was_processed(mailbox_key, item.uid_validity, item.uid):
                continue
            message = parse_email(item.raw)
            result = rspamd.check(item.raw)
            age_days = _age_in_days(item.internal_date, now)
            unread = b"\\Seen" not in item.flags
            if _rspamd_marks_spam(result.action, result.score, result.required_score) and not _is_trusted_sender(
                message.from_addr, rspamd.config.trusted_senders,
            ):
                rule_name, action, target, flag = "rspamd_spam", "move", imap_config.spam_folder, None
            else:
                rules = state.rules()
                rule = next(
                    (candidate for candidate in rules if candidate.condition.strip().lower() != "true"
                     and evaluator.evaluate(candidate, message, result, age_days=age_days, unread=unread)),
                    next((candidate for candidate in rules
                          if evaluator.evaluate(candidate, message, result, age_days=age_days, unread=unread)), None),
                )
                rule_name = rule.name if rule else "no_matching_rule"
                action = rule.action if rule else "none"
                target = rule.target if rule else None
                flag = rule.flag if rule else None
            if action == "paperless":
                _archive_to_paperless(paperless, message, target)
                mailbox.execute_action(item.uid, "move", target, None)
            else:
                mailbox.execute_action(item.uid, action, target, flag)
            if action != "none":
                # messages left in place are re-evaluated on later polls so age-based rules can still fire
                state.mark_processed(mailbox_key, item.uid_validity, item.uid)
                state.log_action(item.uid, message.subject, message.from_addr, result.score, result.action, rule_name, action, target)
            LOGGER.info("uid=%s rule=%s action=%s score=%.2f age_days=%.1f", item.uid, rule_name, action, result.score, age_days)
    except (OSError, RuleError, ValueError) as error:
        LOGGER.exception("processing failure for IMAP host=%r port=%s: %s", imap_config.host, imap_config.port, error)
    finally:
        mailbox.close()


def _archive_to_paperless(paperless: PaperlessClient | None, message: ParsedEmail, target: str | None) -> None:
    if paperless is None:
        raise ValueError("paperless action requires paperless configuration")
    if not target:
        raise ValueError("paperless action requires target folder")
    for attachment in message.attachments:
        paperless.upload_document(attachment.filename, attachment.content, title=message.subject or attachment.filename)


def _age_in_days(internal_date: datetime | None, now: datetime) -> float:
    if internal_date is None:
        return 0.0
    reference = internal_date if internal_date.tzinfo else internal_date.replace(tzinfo=timezone.utc)
    return max((now - reference).total_seconds() / 86400, 0.0)


def _rspamd_marks_spam(action: str, score: float, required_score: float) -> bool:
    return action.lower() in {"reject", "soft reject", "add header", "rewrite subject"} or (
        required_score > 0 and score >= required_score
    )


def _is_trusted_sender(sender: str, trusted_senders: frozenset[str]) -> bool:
    return sender.strip().lower() in trusted_senders


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Rspamd rules to new IMAP mail.")
    parser.add_argument("--config", default="/app/config.yaml")
    run(parser.parse_args().config)
