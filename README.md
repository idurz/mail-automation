# Mail Automation

This project monitors one or more IMAP mailboxes, checks messages with Rspamd, and applies configurable automation rules.

## How It Works

1. The application loads settings from `config.yaml` and environment variables.
2. It connects to each configured IMAP account.
3. It retrieves messages from the selected mailbox, usually `INBOX`.
4. Each message is parsed and sent to Rspamd for spam analysis.
5. Messages identified as spam are moved to the configured spam folder.
6. Non-spam messages are evaluated against the ordered automation rules.
7. The selected action is executed: move, copy, delete, flag, or leave unchanged.
8. Processing history and action logs are stored in SQLite.

The main processing loop is implemented in `app/main.py`.

## Rules

Rules are evaluated in their configured order. Conditions can inspect the message subject, body text, sender, recipient, Rspamd score, Rspamd action, and Rspamd symbols.

Example:

```yaml
- name: move_invoices
  condition: "contains(subject, 'invoice') or contains(text, 'invoice')"
  action: move
  target: Finance
```

Rules can be defined in `config.yaml` or added through the web interface. Rules added through the web interface are stored in SQLite.

## Web Interface

The Flask web interface is normally available at `http://localhost:8080`.

It allows users to add and delete rules, view active rules, view recent mail actions, and create a rule from a previous action.

## Configuration

The default configuration is in `config.yaml`. IMAP and Rspamd settings can also be supplied through environment variables, including `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`, `IMAP_PASSWORD`, `IMAP_ACCOUNTS`, `RSPAMD_URL`, and `RSPAMD_PASSWORD`.

`IMAP_ACCOUNTS` supports a JSON list when multiple accounts are required.

## Running with Docker

`docker-compose.yml` runs two services:

- `mail-automation`, which polls mailboxes and applies rules
- `rspamd`, which analyzes messages for spam

Persistent application state and logs are stored under `/data`. Rspamd data is stored under `/var/lib/rspamd`.

The container starts the application with:

```bash
python -m app.main --config /app/config.yaml
```

## Project Structure

- `app/main.py` - Application entry point and mailbox processing loop
- `app/config.py` - Configuration loading and validation
- `app/imap_client.py` - IMAP connection and mail actions
- `app/email_parser.py` - Email parsing
- `app/rspamd.py` - Rspamd integration
- `app/rules.py` - Rule condition evaluation
- `app/state.py` - SQLite state and action history
- `app/web.py` - Flask API and web server
- `app/templates/index.html` - Web interface
- `config.yaml` - Default application configuration
- `docker-compose.yml` - Container deployment configuration
