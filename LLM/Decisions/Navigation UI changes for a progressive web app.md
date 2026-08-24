# Navigation UI changes for a progressive web app

**Decision**
- **Status:** accepted
- **Live spec:** platform.md §4 Layout
- **What we took:** Top sticky header — Dad4dogs → Home, Check-In, Clients, and ☰ drawer (Billing, Settings, Calendar pending, Contacts). Removed fixed bottom nav. PWA install stays optional; nav must work in Android Chrome tabs.
- **What we left:** Left navigation rail; bottom tabs even in standalone PWA; Billing as a primary header link.
- **Why:** Day-to-day use is Android Chrome in a browser tab; bottom app chrome fights the browser toolbar and is not valuable enough.

---

## What we had (before this decision)

`operations/templates/operations/base.html`:

- Sticky green **header** (“Dad4dogs” + subtitle) — branding only, no destinations
- Fixed **bottom nav** with five tabs: Home · Check-In · Clients · Billing · Settings
- `body` padding-bottom ~80px + safe-area to clear the bar
- PWA install banner / service worker still available, but day-to-day use is often **in-browser**

---

## Why bottom navigation fails here

1. **Chrome UI already owns the bottom.** On Android Chrome, the toolbar / gesture bar / URL chrome compete for the same strip. Our five-tab bar sits under or fights that chrome as the page scrolls (timeline, long client lists, statements).
2. **PWA standalone is optional, not the default.** Bottom nav’s main rescue (“add to home screen so browser chrome disappears”) only helps when David runs installed. He often doesn’t. Designing the primary nav around that mode is the wrong priority.
3. **Five equal tabs are crowded** on a narrow phone. Accidental taps, tiny labels, and no room to grow (Calendar pending, Contacts, etc.).
4. **Desktop / wide Chrome** still shows a fixed bottom bar — awkward mouse travel and wasted vertical space while debugging or reviewing on a laptop.
5. **Thumb-zone theory doesn’t outweigh conflict with the browser.** One-handed reach matters less than “can I see and hit Home without fighting Chrome.”

**Reject for primary nav:** fixed bottom tab bar, left nav rail as the mobile default, and “force PWA so bottom nav works.”

Keep PWA install as a **nice-to-have** (already built). Do not make navigation depend on it.

---

## Proposed direction (Android-browser-first)

### Primary: top app bar with destinations

Fold navigation into the existing sticky header so it lives **above** content and clear of Chrome’s bottom UI.

Suggested layout (mobile):

| Left | Center / flex | Right |
|------|----------------|-------|
| **Dad4dogs** (link → Home) | optional short title | **Menu** (☰) |

Below the title row **or** as a second header row on phones: 2–3 **primary text links** that match the day’s work:

- **Check-In**
- **Clients**
- **Home** (calendar / agenda) — or make Home only the logo tap

Billing and Settings are **not** first-class tabs on the main strip.

### Secondary: hamburger / overflow drawer

Open from ☰ (top-right). List the rest with large tap targets:

- Billing (statements)
- Settings
- Calendar pending (if useful often enough)
- Contacts sync
- Anything else that is occasional

Same drawer on phone and desktop — no separate “rail” required for v1.

### Desktop / wide viewport

Keep **top** navigation (not a left rail unless we later want it). On wider screens the header can show more links inline and hide ☰, or keep ☰ for overflow. Goal: one mental model, not bottom-on-phone / rail-on-desktop.

### Spacing / CSS consequences

- Remove fixed `nav.bottom-nav` and the large `padding-bottom` reserved for it
- Keep `safe-area-inset-top` on the sticky header
- Primary links: readable (~0.9rem+), active state = brand color / underline — match existing density rules (not another padded card strip)

---

## Out of scope for this change

- Redesigning Check-In CTAs, dense lists, or labeled detail cards
- Requiring PWA install
- Adding icons-only bottom tabs “to save space”
- Customer-facing feed chrome (public templates stay separate)

---

## Acceptance criteria (when David says implement)

1. On a phone-width viewport in Chrome, **no fixed bottom app nav**; all destinations reachable from the **top** (links + ☰).
2. Check-In and Clients remain one tap from any staff page without opening the drawer.
3. Billing and Settings live in the drawer (or equivalent overflow), not as equal peers of Check-In.
4. Main content can scroll to the last line without being covered by app chrome at the bottom (browser chrome may still show — that is OK).
5. Active page still visually indicated.
6. `platform.md` updated as the live nav rule; this file moves to `LLM/Decisions/` with a Decision header.

---

## Decision needed before coding

Confirm the **primary strip** (logo + which 2–3 links) and the **drawer list**. Default recommendation if no further preference:

- Header: logo → Home · **Check-In** · **Clients** · ☰  
- Drawer: Billing · Settings · Calendar pending · Contacts
