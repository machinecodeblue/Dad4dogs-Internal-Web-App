# Dad4dogs Internal Web App — LLM Project Guide

**Owner:** David — Dad4dogs  
**Last updated:** August 2026  
**Audience:** LLM assistants and future maintainers

This is the **single entry point** for understanding this codebase. Domain-specific detail lives in separate files — read those when working in that area.

---

## 1. What This App Is

A **Django 5 monolith** for David's single-user dog boarding operation (~25 repeat clients).

| Principle | Detail |
|-----------|--------|
| **Persona** | David-only, mobile-first, **one-handed** (phone in one hand, dogs in the other) |
| **Database** | SQLite |
| **Timezone** | `America/Toronto` |
| **Scale** | ~25 dogs; capacity warns above **standard** (default 8) and blocks above **insurance max** (default 10) — both editable in Settings |
| **Architecture** | One app (`operations`) split by **domain packages** — never monolithic 500-line files |

**Core domains:**

| Domain | Covers |
|--------|--------|
| **Customers** | Owners, dogs, COI, vaccinations, Google Contacts import |
| **Scheduling** | Visits, repeat series, dashboard, check-in/out, pricing, calendar |
| **Billing** | Weekly statements, checkout fees (pricing engine lives in scheduling) |
| **Admin** | Business baseline — identity, address, hours, phone numbers, documents (planned) |
| **Feed** | Staff timeline capture + customer photo feed (secret link, no password) |

---

## 2. Read Order for LLM Sessions

1. **This file** (`PROJECT.md`) — context and file map
2. **Domain file** for the area you are changing:
   - `customers.md` — owners, dogs, COI, vax, contacts
   - `scheduling.md` — visits, agenda, check-in/out guards, pricing, email confirmations
   - `billing.md` — statements
   - `admin.md` — business settings, baseline contact info, documents (planned)
   - `feed.md` — timeline capture, customer photo feed, speakable URLs
3. **`platform.md`** — dev server, HTTPS, ngrok, Gmail OAuth, PWA, **cognitive-load UX rules**, testing. Any list/detail/dashboard/check-in template change must follow those rules.

Do **not** treat `Proposed work/` or `Decisions/` as the live spec. Open proposals are evaluation-only; decided notes are history. Standing rules live in this file and the domain markdown.

Do **not** change pricing tiers, pipeline stages, or visit status guards unless David explicitly asks. Daily capacity (standard + insurance max) is edited on **Settings** — do not hardcode 8/10 in templates or `capacity.py` checks.

---

## 3. Domain Package Layout (Code)

Code is organized by domain in **models**, **forms**, and **views**:

```
operations/
├── models/
│   ├── __init__.py       # re-exports all models
│   ├── customers.py      # CustomerOwner (incl. structured address), ClientProfile, VaccinationRecord
│   ├── scheduling.py     # VisitSeries, Visit, TimelineMediaAsset, VisitTimelineEvent, PendingCalendarEvent
│   ├── billing.py        # AccountStatement
│   └── business.py       # BusinessProfile (singleton)
├── forms/
│   ├── __init__.py
│   ├── customers.py      # CustomerOwnerForm (structured address), DogProfileForm, VaccinationRecordForm
│   ├── intake.py         # IntakeWizardForm (new client & dog)
│   ├── scheduling.py     # VisitForm, TimelineMomentForm, TimelineForwardForm
│   └── business.py       # BusinessProfileForm
├── views/
│   ├── __init__.py       # urls.py imports from here
│   ├── customers.py      # clients, dogs, COI, vax, contacts, feed link regenerate
│   ├── scheduling.py     # dashboard, check-in, visits, timeline, calendar, iCal
│   ├── customer_feed.py  # public customer photo feed
│   ├── billing.py        # statements
│   ├── business.py       # business_settings
│   └── pwa.py            # manifest.webmanifest, sw.js
├── services/             # business logic — prefer adding here over bloating views
│   ├── timeline_media.py, timeline_visits.py, geolocation.py
│   ├── addresses.py, phones.py, feed_slugs.py, feed_access.py
│   └── visit_email.py, gmail_send.py, …
├── pricing.py            # tiered fee engine (scheduling domain)
├── capacity.py           # daily dog count guards (scheduling domain)
└── templates/operations/
```

**Rule for new code:** add to the matching domain file. If a file grows past ~200 lines, split further within that domain — do not merge domains.

---

## 4. Project Tree (source only)

Regenerate with: `tree /F /A > project_schema.txt` from project root.

```
Dad4dogs Internal Web App/
├── config/                 # Django settings, root URLs
├── operations/             # All business logic (see §3)
├── LLM/                    # Instruction sets (this folder)
├── O-Auth Key/             # Gmail OAuth credentials + token (gitignored)
├── certs/                  # mkcert HTTPS certs (gitignored)
├── scripts/                # setup-certs.ps1, run-dev-tunnel.ps1
├── Data samples/           # google_contacts.csv reference
├── oauth_setup.py          # One-time Gmail OAuth browser flow
├── manage.py
└── requirements.txt
```

---

## 5. Business Rules Summary (do not change casually)

### Pipeline (per dog)
Inquiry → Meet & Greet → Evaluation → Approved

### Pricing (CAD, at checkout)
| Tier | Rule | Rate |
|------|------|------|
| Short | ≤ 4 hours (not overnight) | $15 |
| Daytime | ≤ 12 hours (not overnight) | $25 |
| Overnight | Crosses 11 PM–4 AM **or** starts before 4 AM | $37.50 |

Overnight is evaluated **before** hour tiers. Multi-day: each full 24h = Overnight; remainder priced separately.

### Customer vs dog (critical)
- **Customer** (`CustomerOwner`) = one per `owner_email`; owns COI
- **Dog** (`ClientProfile`) = `owner_email` + `dog_name`; owns pipeline, visits, vaccinations
- A customer may have **zero dogs** until David adds one
- Never invent a dog from the owner's first name on import
- **Standard stays (VisitForm create):** dog must be Approved, have current validated vaccination, and owner COI received — see `customers.md` / `scheduling.md`

### Visit status transitions (critical)
`scheduled` → `checked_in` → `completed` (or `cancelled`).

- `check_in()` only from `scheduled`; `check_out()` only from `checked_in` with no existing `calculated_fee`
- Illegal calls raise `ValidationError` and must not overwrite `actual_arrival`, `actual_departure`, or `calculated_fee`
- `check_out()` refreshes from the DB first so a stale instance cannot re-price a finalized visit
- Views catch that error and redirect — no 500 on a mobile double-tap
- Do not set those fields (or `status`) in views to bypass the methods
- Capacity is enforced on **booking** saves, not on check-in/out `update_fields` — a full day must not block checkout
- `VisitForm.save_all()` may pass `skip_capacity=True` after `clean()` already checked every occurrence; clone/admin/direct `save()` must not

---

## 6. Implementation Status

| Feature | Status |
|---------|--------|
| Customer/dog split UI | Done |
| New Client & Dog intake | Done — `/clients/intake/`, optional Meet & Greet visit |
| Vaccination expiry tracking | Done — dashboard 30-day / expired cards; `/clients/?vax=` |
| Structured owner address | Done — street / unit / city / province / postal; Maps + statements + vCard |
| Soft-hide dogs | Done — `is_hidden`; no UI hard-delete (visits/photos stay) |
| Pipeline per dog, COI per customer | Done |
| Visit booking (natural-language Start/End) | Done |
| Repeat series (daily/weekly/weekdays/monthly) | Done |
| Dashboard month calendar + daily agenda | Done |
| Mobile check-in/out + auto pricing | Done — status guards on `check_in()` / `check_out()` |
| Booking confirmation email (Gmail OAuth) | Done |
| Google Contacts selective import + vCard | Done |
| iCal outbound `/ical/` | Done |
| HTTPS dev server + ngrok | Done |
| Business settings (`/settings/`) | Done — identity, address, hours, phones, daily capacity |
| Booking iCal LOCATION + ORGANIZER from settings | Done — `BusinessProfile` → `visit_email.py` |
| Contemporaneous timeline (staff capture) | Done — photo/video, GPS, multi-dog, forward |
| Customer photo feed (secret link) | Done — `/feed/<secret>/<dog>/`, full history |
| Owner emergency + per-dog vet contacts | Done — see `customers.md` §2 |
| Feed access stats (visitor cookie) | Done — views + distinct browsers on dog detail |
| PWA install (David's phone) | Done — manifest, service worker, install banner |
| Business document uploads (COI, etc.) | Not started |
| Calendar inbound `.ics` import command | Partial — file-based, not live Gmail |
| Weekly statement **email send** | Partial — generates + formats; send not wired |
| Feed reactions, comments, public share (re-share, download) | Done — `/feed/share/<token>/`, `dad4dogs_<uuid>.jpg` — see `feed.md` |
| Feed push notifications | Planned |
| GoDaddy inquiry parsing | Not started |
| e-Transfer automation | Not started |

---

## 7. Quick Commands

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver_https 9000          # local HTTPS
ngrok http https://127.0.0.1:9000              # mobile tunnel
python oauth_setup.py                          # first-time Gmail token
python manage.py gmail_auth --test you@email.com
python manage.py test operations
```

Set feed links in booking emails (ngrok or production):
```bash
$env:PUBLIC_SITE_URL = "https://your-subdomain.ngrok.app"
```

---

## 8. LLM Session Checklist

1. Identify the **domain** before editing (customers / scheduling / billing / admin / platform).
2. Open the matching `LLM/<domain>.md` file.
3. Keep **mobile-first, one-handed** UX — no desktop-only patterns, no dashboard sprawl. Standing rules in `platform.md` (accepted from Decisions; do not re-read Proposed work as spec):
   - Detail screens: ≤5 primary fields above the fold (name, tap-to-call mobile, emergency call). Customer **Edit** beside the name (existing edit form). Customer address/email stay visible. Customer **COI:** warn if missing; **✓** beside the name if received. Dog feed/hide/vCard stay in `<details>`.
   - Client list: compact `Dog · Owner · badge · phone` rows. No nested cards. Filters in a disclosure if more than 2.
   - ≤2 primary CTAs per card. Dangerous/admin actions in **More actions**.
   - ≤2 badges, and only for work that still needs doing (no green OK / COMPLETED / OK VAX).
   - List notes: one line + `.truncate`. Reuse `.compact-row`, `details.disclosure`, `.admin-drawer`.
4. Visit booking stays **two free-text fields** (Start/End) — no multi-step pickers.
5. No bulk Google contact import without preview + checkboxes.
6. Extend `operations/services/` for new business logic.
7. Add tests in `operations/tests.py` for pricing, capacity, forms, or imports you touch. Capacity occupancy/blocks must follow Settings (`capacity_limits()`), not hardcoded 8/10.
8. Do not bypass `Visit.check_in()` / `check_out()` status guards.
9. Do not re-run `full_clean()` / capacity on check-in or check-out saves.
10. Do not pass `skip_capacity=True` except from `VisitForm.save_all()`.
11. Never commit `O-Auth Key/`, `certs/`, or live client PII.

---

## 9. Domain Instruction Files

| File | Contents |
|------|----------|
| [`customers.md`](customers.md) | Owners, dogs, COI, vaccinations, contacts import |
| [`scheduling.md`](scheduling.md) | Visits, repeat, dashboard, check-in/out status guards, pricing, **capacity limits from Settings**, calendar, booking email |
| [`billing.md`](billing.md) | Weekly statements, checkout totals |
| [`admin.md`](admin.md) | Business settings, baseline contact info, **daily capacity** (standard + insurance max), documents |
| [`feed.md`](feed.md) | Staff timeline, customer feed, speakable URLs, access logging |
| [`platform.md`](platform.md) | Dev environment, HTTPS, ngrok, PWA, Gmail, **cognitive-load UX**, testing |
| [`Proposed work/`](Proposed%20work/) | **Inbox of proposals** — evaluate only; not standing spec. Empty of a topic means that idea is not on the table. See `Proposed work/README.md`. |
| [`Decisions/`](Decisions/) | **Archive** of accepted, rejected, or partial proposals. History only. Live rules stay in the domain files named in each Decision header. |

---

## 10. Proposed work and Decisions

`LLM/Proposed work/` is a list of **ideas we might put in the app**. Read it only when David asks to evaluate a proposal. Do not code from it on a normal change.

When a proposal is decided (yes, no, or partial):

1. Write any accepted rules into the matching domain file (`platform.md`, `customers.md`, …). That file becomes the live spec.
2. Move the markdown into `LLM/Decisions/`, keeping the original filename (no `accepted-` / `1_` prefixes).
3. Add a **Decision** header at the top: status, what we took, what we left, why, and where the live spec lives.
4. Delete it from Proposed work so the inbox only holds open ideas.

Partial work uses the same folder: the header says **partial** and lists what landed vs what did not. Rejected notes also go here with status **rejected** — one archive, not two.

Do not edit a Decisions file to change the product. Edit the domain file named in its header.