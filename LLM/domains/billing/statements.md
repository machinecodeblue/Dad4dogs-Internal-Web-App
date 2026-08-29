# Billing: Statements (compile & UI)

**Load for:** weekly compile, list/detail screens, line-item shape.  
**Related:** [`email.md`](email.md), [`../scheduling/pricing.md`](../scheduling/pricing.md)

---

## Generation

```bash
python manage.py generate_statements
```

- `services/statements/compile.py` — `generate_weekly_statements()`
- Groups completed visits by dog (`client_id`) for the week (`weeks.week_bounds`)
- Sets `send_status = queued` on create/update
- Snapshots Visit fees — does **not** call `pricing_engine` again
- Line item fields: `visit_id`, `date`, `arrival`, `departure`, `fee`, `breakdown`, and when linked: `service_name`, `service_slug`

Day filter uses `actual_departure__date` within the week window.

---

## Screens & URLs

| Path | Methods | Purpose |
| --- | --- | --- |
| `/statements/` | GET | Dense list — dog name link, week, total; amber badge if not `sent` |
| `/statements/<id>/` | GET | Detail, line items, email preview, send CTA |
| `/statements/<id>/send/` | POST | Send via Gmail (see [`email.md`](email.md)) |

Drawer **Billing** links here (not bottom-nav — `platform.md`).

### Views

| Callable | Module | Role |
| --- | --- | --- |
| `statements_list` | `list.py` | Dense list |
| `statement_detail` | `detail.py` | Detail + preview |
| `statement_send_email` | `actions.py` | Thin POST → `statements.send` |
| `get_unbilled_summary_for_client` | `helpers.py` | Wraps `statements.unbilled` |

---

## Unbilled summary (B2)

`get_unbilled_summary_for_client(client_id)` → count + total of **completed** visits whose `visit_id` is not present in any of that dog’s statement `line_items`. Surfaced on statement list when any unbilled totals exist (compact muted line), and on dog-related billing context when useful.

---

## LLM rules

1. Keep `views/billing/actions.py` thin — send/orchestration in `services/statements/`.
2. Do not invent portable export or e-Transfer here (see [`roadmap.md`](roadmap.md)).
3. Regenerating a week overwrites line items from current Visit fees (corrected checkouts flow through).
