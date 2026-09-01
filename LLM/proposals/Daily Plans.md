# Plan: Product backlog — next application steps

## Where we are

Core operator loop is **live and Done** per `LLM/PROJECT.md` §5: customers/intake/pipeline, vaccinations, visit booking + repeats, dashboard agenda, check-in/out, confirmation email + outbound `/ical/`, feed + PWA, tenant schema Phase 1, capacity settings, services catalog Phase 1–3 (pricing engine, capacity exempt, statement service lines), weekly statements B1–B3, Meet & Greet / Evaluation booking screens.

**Open queue:** this file (`Daily Plans.md`) plus `README.md`. Recent commits landed intake, M&G, billing modularization, and the `dogs/` package split. Capacity logic now lives in `operations/capacity/`; tests are splitting into `operations/tests/`.

**Hygiene (David):** commit capacity package + M&G occupancy behaviour; remove legacy `operations/tests.py` monolith once the package is the runner. **Doc drift (agent):** done — live domains/PROJECT no longer claim exempt/B3 unbuilt; paths point at `capacity/` and `tests/`.

---

## Priority lens

Ranked for **single-operator daily boarding first**, then platform hardening, then deferred product bets that need clearer rules. Multi-tenant auth and SQLite export stay valuable but do not unblock today’s desk work.

---

## P0 — Hygiene (hours, not a product epic)

| Item | Why | Status |
| --- | --- | --- |
| Commit capacity package + M&G occupancy | Behavior matches product rule | **David** — `operations/capacity/`, delete legacy `tests.py` when ready |
| Doc drift cleanup | Status / paths contradicted live code | **Done** — services, scheduling index, admin, PROJECT, platform, contacts, billing, feed, capacity.md |

No new feature work required for P0.

---

## P1 — Daily ops gaps (highest product value)

### 1. Calendar inbound completion (Partial → Done)

**Today:** File import → `PendingCalendarEvent` → review/approve at `/calendar/pending/`. Helpers in `gmail_sync.py`; **no live Gmail calendar read**.

**Next slices (smallest first):**
1. Live Gmail calendar poll / pull into pending (same approve UX).
2. Harden approve path edge cases (capacity ValidationError already caught).

**Why first:** Reduces double-entry between Google Calendar and the app. Spec already partial; infrastructure half-built.

**Refs:** `PROJECT.md` (Partial), `scheduling/calendar_email.md` Inbound, `gmail_sync.py`.

### 2. Booking calendar METHOD:UPDATE / CANCEL

**Today:** Confirmations send `METHOD:REQUEST` only. Reschedule/cancel does not update the client’s calendar invite.

**Why:** Stops stale invites after real schedule changes — high trust issue with owners.

**Refs:** `scheduling/calendar_email.md`, `scheduling/index.md` Not yet built.

### 3. Edit / delete entire repeat series

**Today:** Series create works; per-visit edit/delete only.

**Why:** Common correction path (“move the whole weekly run”) without N clicks and capacity thrash.

**Refs:** `scheduling/booking.md`, `scheduling/index.md`.

---

## P2 — Platform (when ops P1 is stable or before a second workspace)

| Item | Status | Notes |
| --- | --- | --- |
| Default tenant QuerySet / middleware | Planned | Enforce `tenant=` everywhere by default; reduce foot-guns | `admin.md`, `PROJECT.md` |
| Multi-tenant auth & membership | Planned | Real login ↔ workspace; blocks inventing a second workspace in app code | `admin.md` |
| Production media auth | Not built | Proxy / signed URLs so `/media/` is not open outside DEBUG | `feed.md` §10 |
| Deployment notes | Future | `platform.md` §10 |

Do **not** invent a second workspace until membership exists (`admin.md` rule 1).

---

## P3 — Billing & portability (deferred until product rules exist)

| ID | Slice | Blocker |
| --- | --- | --- |
| **B4** | Adhoc statement generate | Product rules TBD |
| **B5** | Portable SQLite export | PROJECT Rule C; single-operator today — useful but not daily |
| **B6** | e-Transfer automation | Needs stable send + payment rules |

**Refs:** `billing/roadmap.md`. Prefer leaving deferred until David defines B4/B6 rules.

---

## P4 — Nice-to-have / scale later (do not start unless asked)

From `customers.md` / `feed.md` “Not yet built”:

- PDF/image upload for vet papers
- Vaccination expiry email/SMS alerts
- Multiple emergency contacts
- PWA / web-push “new photo” alerts
- Comment moderation / per-moment `published` flag
- Capacity futures: weekday staff overrides, isolation buffer, weather modes (`admin.md`)

These are correctly parked at current ~8-dog scale.

---

## Suggested sequence (next 3–5 sessions)

```
P0 commit + doc drift
    → P1.1 live Gmail calendar inbound
    → P1.2 METHOD:UPDATE/CANCEL
    → P1.3 series edit/delete
    → (optional) P2 tenant QuerySet  OR  B5 SQLite if portability becomes urgent
```

Each P1 item should stay a **small package**: proposal (if behavior is ambiguous) → implement → archive decision → update domain topic only.

---

## Explicitly not next

- Re-opening intake / M&G / Evaluation booking (shipped; Phase 3 agenda badges marked wontfix earlier).
- Re-splitting scheduling/billing LLM packages (already done).
- Auto-advancing pipeline stages (standing preference: explicit Pass/Approve only).
- Billing B4–B6 without new product rules from David.

---

## Decision needed from you

Pick the **first implementation target** after P0 hygiene:

1. **Live Gmail calendar inbound** (finish Partial)
2. **METHOD:UPDATE/CANCEL** (calendar honesty on change)
3. **Series edit/delete** (booking UX)
4. **Tenant QuerySet Phase 2** (platform)
5. **Something else** (e.g. B5 SQLite, vet paper uploads)

Once chosen, that item becomes the next concrete implementation plan (or a short proposal if rules are still fuzzy).
