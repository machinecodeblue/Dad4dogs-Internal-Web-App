# Proposed work

Inbox of **ideas under discussion** — not standing product spec.

Drop a markdown file here when something is proposed for the app. Assistants must **not** implement from this folder unless David asks to evaluate or apply a specific proposal.

Everyday coding uses `PROJECT.md` and the domain files (`customers.md`, `scheduling.md` + `scheduling/`, `billing.md` + `billing/`, `platform.md`, …).

After a decision (accept, reject, or partial):

1. Put the live rules into the matching domain file if anything was accepted.
2. Move this markdown into `LLM/decisions/` (keep the original filename when practical).
3. Add a **Decision** header at the top: status, what landed, why, where the live spec is now, and any **wontfix** items.
4. Delete it from this folder so Proposed work only holds open ideas.

Settled intake / Meet & Greet / scheduling-doc packaging work lives under `LLM/decisions/` — do not re-drop those files here.
