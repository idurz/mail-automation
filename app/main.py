from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import signal
import time

from .config import load_config
from .config import ImapConfig
from .email_parser import parse_email
from .imap_client import MailboxClient
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
    evaluator = RuleEvaluator()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while RUNNING:
            for imap_config in config.imap_accounts:
                if RUNNING:
                    _process_mailbox(imap_config, state, rspamd, evaluator)
            if RUNNING:
                time.sleep(min(account.poll_interval for account in config.imap_accounts))
    finally:
        state.close()


def _process_mailbox(
    imap_config: ImapConfig, state: ProcessingState, rspamd: RspamdClient, evaluator: RuleEvaluator,
) -> None:
    mailbox = MailboxClient(imap_config)
    mailbox_key = f"{imap_config.username}@{imap_config.host}/{imap_config.mailbox}"
    try:
        mailbox.connect()
        LOGGER.info("connected to %s mailbox %s", imap_config.host, imap_config.mailbox)
        for item in mailbox.new_messages():
            if state.was_processed(mailbox_key, item.uid_validity, item.uid):
                continue
            message = parse_email(item.raw)
            result = rspamd.check(item.raw)
            if _rspamd_marks_spam(result.action, result.score, result.required_score):
                rule_name, action, target, flag = "rspamd_spam", "move", imap_config.spam_folder, None
            else:
                rule = next((candidate for candidate in state.rules() if evaluator.evaluate(candidate, message, result)), None)
                rule_name = rule.name if rule else "no_matching_rule"
                action = rule.action if rule else "none"
                target = rule.target if rule else None
                flag = rule.flag if rule else None
            mailbox.execute_action(item.uid, action, target, flag)
            state.mark_processed(mailbox_key, item.uid_validity, item.uid)
            state.log_action(item.uid, message.subject, message.from_addr, result.score, result.action, rule_name, action, target)
            LOGGER.info("uid=%s rule=%s action=%s score=%.2f", item.uid, rule_name, action, result.score)
    except (OSError, RuleError, ValueError) as error:
        LOGGER.exception("processing failure for IMAP host=%r port=%s: %s", imap_config.host, imap_config.port, error)
    finally:
        mailbox.close()


def _rspamd_marks_spam(action: str, score: float, required_score: float) -> bool:
    return action.lower() in {"reject", "soft reject", "add header", "rewrite subject"} or (
        required_score > 0 and score >= required_score
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Rspamd rules to new IMAP mail.")
    parser.add_argument("--config", default="/app/config.yaml")
    run(parser.parse_args().config)
