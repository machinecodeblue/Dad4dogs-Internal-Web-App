# Billing: Statement email

**Load for:** email body format, Gmail send, status transitions.  
**Code:** `services/statements/format.py`, `services/statements/send.py`, `services/gmail_send.py`

---

## Format

`format_statement_email(statement)` → plain-text body:

- Header, week range, owner, dog, email
- Owner `Address:` (one-line) from `CustomerOwner` when on file
- Visit lines: date, fee; include service name when `service_name` is on the line item
- Total due + e-Transfer reminder

Subject: `Dad4dogs statement — {dog} — week of {week_start}`

---

## Send (B1)

`send_statement_email(statement)`:

1. Require `client.owner_email`
2. Format body + subject
3. `gmail_send.send_gmail(subject, body, to=owner_email)`
4. On success: `send_status=sent`, `sent_at=now`, save
5. On `GmailSendError`: raise `StatementEmailError` — **statement unchanged**; view flashes warning, never 500

View: `POST /statements/<id>/send/` → redirect to detail. Already-`sent` may re-send only if David asks later; default: allow re-send and refresh `sent_at` (idempotent success) **or** no-op with info — **prefer:** re-send allowed, update `sent_at`.

Reuse OAuth stack:

- `operations/services/gmail_send.py`
- `python manage.py gmail_auth --test` / `python oauth_setup.py`

Do **not** attach iCal for statements (booking invites only).

---

## Tests

Mock `send_gmail`; assert status/`sent_at`; assert OAuth failure leaves statement queued/draft and returns redirect with message.
