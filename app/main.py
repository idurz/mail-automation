from __future__ import annotations

import argparse
import logging
from logging.handlers import RotatingFileHandler
import signal
import time

from .config import load_config
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
    state = ProcessingState(config.state.db_path)
    state.seed_rules(config.rules)
    start_server(state, config.web_port)
    mailbox = MailboxClient(config.imap)
    rspamd = RspamdClient(config.rspamd)
    evaluator = RuleEvaluator()
    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    try:
        while RUNNING:
            try:
                mailbox.connect()
                LOGGER.info("connected to %s mailbox %s", config.imap.host, config.imap.mailbox)
                while RUNNING:
                    for item in mailbox.new_messages():
                        if state.was_processed(config.imap.mailbox, item.uid_validity, item.uid):
                            continue
                        message = parse_email(item.raw)
                        result = rspamd.check(item.raw)
                        if _rspamd_marks_spam(result.action, result.score, result.required_score):
                            rule_name, action, target, flag = "rspamd_spam", "move", config.imap.spam_folder, None
                        else:
                            rule = next((candidate for candidate in state.rules() if evaluator.evaluate(candidate, message, result)), None)
                            rule_name = rule.name if rule else "no_matching_rule"
                            action = rule.action if rule else "none"
                            target = rule.target if rule else None
                            flag = rule.flag if rule else None
                        mailbox.execute_action(item.uid, action, target, flag)
                        state.mark_processed(config.imap.mailbox, item.uid_validity, item.uid)
                        state.log_action(item.uid, message.subject, message.from_addr, result.score, result.action, rule_name, action, target)
                        LOGGER.info("uid=%s rule=%s action=%s score=%.2f", item.uid, rule_name, action, result.score)
                    time.sleep(config.imap.poll_interval)
            except (OSError, RuleError, ValueError) as error:
                LOGGER.exception(
                    "processing failure for IMAP host=%r port=%s; reconnecting: %s",
                    config.imap.host,
                    config.imap.port,
                    error,
                )
                mailbox.close()
                if RUNNING:
                    time.sleep(config.imap.poll_interval)
    finally:
        mailbox.close()
        state.close()


def _rspamd_marks_spam(action: str, score: float, required_score: float) -> bool:
    return action.lower() in {"reject", "soft reject", "add header", "rewrite subject"} or (
        required_score > 0 and score >= required_score
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Apply Rspamd rules to new IMAP mail.")
    parser.add_argument("--config", default="/app/config.yaml")
    run(parser.parse_args().config)
