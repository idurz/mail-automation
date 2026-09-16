# Mail Automation

Mail Automation watches one or more IMAP mailboxes, screens every new message with [Rspamd](https://rspamd.com/), and then applies your own ordered rules to decide what happens to it — move it to a folder, copy it, flag it, delete it, or archive its attachments to [Paperless-ngx](https://docs.paperless-ngx.com/). It's meant to run continuously (e.g. in Docker) as a lightweight inbox triage layer in front of whatever mail client you use.

## How It Works

1. The application loads settings from `config.yaml` and environment variables.
2. It connects to each configured IMAP account.
3. It retrieves messages from the selected mailbox, usually `INBOX`.
4. Each message is parsed and sent to Rspamd for spam analysis.
5. Messages Rspamd flags as spam (reject, soft reject, add header, rewrite subject, or a score at/above the required threshold) are moved straight to `imap.spam_folder`, skipping the rules below. Senders listed in `rspamd.trusted_senders` are exempt from this automatic move and continue to the ordinary rules.
6. Everything else is evaluated against your ordered automation rules; the first matching rule wins.
7. The rule's action is executed: `move`, `copy`, `delete`, `flag`, `paperless`, or `none` (leave it alone).
8. Every UID is only ever fetched again until it produces an action other than `none` — messages that don't yet match anything are re-checked on each poll, which is what lets age-based rules (see below) eventually catch up with them.
9. Processing history, action logs, and rules added through the web UI are stored in SQLite.

The main processing loop is implemented in `app/main.py`.

## Rules

Rules are evaluated **in order**, and the **first matching rule wins** — later rules are not evaluated once a match is found. A rule whose `condition` is literally `"true"` is treated as a catch-all: it's only used as a fallback after every other rule has been checked, regardless of where it sits in the list, so put it last for clarity anyway. A rule condition of `"false"` never matches.

### Writing a condition

Conditions are a small boolean expression language (not full Python) evaluated against the current message. Available fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `subject` | string | Message subject |
| `text` | string | Plain-text body |
| `from_addr` | string | Sender email address |
| `from_name` | string | Sender display name |
| `to_addr` | string | Recipient address |
| `size` | number | Raw message size in bytes |
| `score` | number | Rspamd score |
| `required_score` | number | Rspamd's spam threshold |
| `rspamd_action` | string | Rspamd's verdict, e.g. `"no action"` |
| `symbols` | dict | Rspamd symbols that fired |
| `age_days` | number | Days since the message arrived (from the IMAP `INTERNALDATE`) |
| `unread` | boolean | `true` if the message's `\Seen` flag is not set |

Supported operators: `and`, `or`, `not`, comparisons (`==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`). Supported helper functions:

- `contains(value, text)` — case-insensitive substring check, e.g. `contains(subject, 'invoice')`
- `has_symbol('SYMBOL_NAME')` — true if that Rspamd symbol fired on the message

Conditions are parsed as a restricted Python expression, so only the constructs above are accepted — arbitrary Python is rejected.

### Actions

| Action | `target` | `flag` | Effect |
| --- | --- | --- | --- |
| `none` | — | — | Leave the message where it is; re-evaluated on the next poll |
| `move` | required | — | Move the message to the `target` folder |
| `copy` | required | — | Copy the message to the `target` folder, leave the original in place |
| `delete` | — | — | Permanently delete the message |
| `flag` | — | optional | Add an IMAP flag (defaults to `\Flagged`) |
| `paperless` | required | — | Upload every attachment to Paperless-ngx, then move the message to the `target` folder |

### Examples

```yaml
rules:
  # Move anything invoice-related to a Finance folder
  - name: move_invoices
    condition: "contains(subject, 'invoice') or contains(text, 'invoice')"
    action: move
    target: Finance

  # Delete messages that have sat unread for 30 days
  - name: delete_unread_after_30_days
    condition: "unread and age_days >= 30"
    action: delete

  # Delete anything older than a year, read or not
  - name: delete_older_than_1_year
    condition: "age_days >= 365"
    action: delete

  # Delete messages older than 14 days from a specific sender/domain
  - name: delete_old_newsletters
    condition: "age_days >= 14 and contains(from_addr, 'newsletter@x.com')"
    action: delete

  # Archive attachments to Paperless-ngx, then move the email out of the inbox
  - name: archive_statements_to_paperless
    condition: "contains(subject, 'statement')"
    action: paperless
    target: Archive

  # Catch-all: leave anything else untouched
  - name: default
    condition: "true"
    action: none
```

`age_days` and `unread` make it possible to express "clean up old mail" policies purely in rules, without any extra tooling — because unmatched messages (action `none`) are re-checked on every poll rather than being skipped forever, a message that's too new today will naturally start matching an age-based rule once it's old enough.

Rules can be defined in `config.yaml` (loaded once, at first startup, to seed SQLite) or added/removed through the web interface, where they're stored directly in SQLite. The web UI only builds simple `contains(...)` conditions on the built-in fields (subject, text, from address, sender name); for `age_days`/`unread`/`has_symbol`/score comparisons, edit `config.yaml` and restart, or add the rule directly via the `/api/rules` API.

The `paperless` action uploads each attachment on a matching message to a Paperless-ngx instance via its `/api/documents/post_document/` endpoint, then moves the message out of the inbox to the rule's `target` folder (for example `Archive`). Configure the integration under `paperless` in `config.yaml`, or with the `PAPERLESS_URL` and `PAPERLESS_TOKEN` environment variables.

## Web Interface

The Flask web interface is normally available at `http://localhost:8080`.

It allows users to add and delete rules, view active rules, view recent mail actions, and create a rule from a previous action.

## Configuration

The default configuration is in `config.yaml`. IMAP and Rspamd settings can also be supplied through environment variables, including `IMAP_HOST`, `IMAP_PORT`, `IMAP_USERNAME`, `IMAP_PASSWORD`, `IMAP_ACCOUNTS`, `RSPAMD_URL`, and `RSPAMD_PASSWORD`. Paperless settings can be supplied through `PAPERLESS_URL` and `PAPERLESS_TOKEN`.

`IMAP_ACCOUNTS` supports a JSON list when multiple accounts are required.

To keep known contacts out of the automatic spam move, list their exact email addresses under `rspamd.trusted_senders`:

```yaml
rspamd:
  trusted_senders:
    - colleague@example.com
    - billing@vendor.example
```

Address comparisons are case-insensitive. This is an exact-address allowlist: trusted messages still receive their Rspamd score and are evaluated by your normal rules.

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
- `app/paperless.py` - Paperless-ngx document upload integration
- `app/rules.py` - Rule condition evaluation
- `app/state.py` - SQLite state and action history
- `app/web.py` - Flask API and web server
- `app/templates/index.html` - Web interface
- `config.yaml` - Default application configuration
- `docker-compose.yml` - Container deployment configuration
