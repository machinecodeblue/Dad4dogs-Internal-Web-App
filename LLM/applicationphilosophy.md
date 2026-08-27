# Application Philosophy

**Audience:** LLM assistants and maintainers  
**Status:** Standing convention — how we write and shape code for Dad4dogs  
**Not:** product features, pricing rules, or domain workflows (those live in domain `.md` files)

This file is the project’s **development philosophy**: preference for small, auditable units, convention over configuration, and structure that supports SOC 2–oriented clarity (boundaries you can explain and review). It is intentionally **separate** from `PROJECT.md` so the map stays a map and the philosophy stays a philosophy.

---

## 1. Why this exists

We build with LLMs in the loop. That is powerful and also easy to thrash: one “just add it here” change after another grows a module until nobody (human or model) can honestly say what the file is for.

**Dad4dogs preference:** be aggressive and proactive about structure. Split early. Prefer many small files with clear jobs over one convenient pile. David audits by opening a file and checking that it does what its name and docs claim.

SOC 2–minded software needs the same habit: clear boundaries, reviewable units, and no “god” modules that mix unrelated concerns.

---

## 2. Small files, one job each

* Prefer **small, simple files**.
* A file should have a **single, nameable job**. If you cannot say the job in one short phrase, the file is doing too much.
* When a file approaches **~150–200 lines**, split it **before** it becomes a monolith — do not wait until it hurts.
* Do not grow “god modules” (one file that owns unrelated screens, domains, or layers).

**Audit test:** open the file; skim imports and top-level names; confirm they match the claimed job. If they do not, refactor or stop and ask.

---

## 3. Domain packages + stable public surface

Reference pattern already in the tree:

| Package | Shape |
|---------|--------|
| `operations/views/scheduling/` | `dashboard`, `checkin`, `visits`, `timeline`, `calendar`, `helpers` + `__init__.py` |
| `operations/views/customers/` | `clients`, `intake`, `vaccinations`, `contacts`, `actions` + `__init__.py` |
| `operations/views/feed/` | `private`, `public`, `helpers` + `__init__.py` |

**Convention:**

1. Split by **domain concern** into a directory package.
2. Keep an `__init__.py` that **re-exports** the public callables (and keep `__all__` honest).
3. External imports (`urls.py`, other apps) should keep working through that stable surface — refactor internals without thrashing call sites.
4. Same idea applies to `models/`, `forms/`, and `services/` as they grow: package by domain, re-export, do not merge domains.

`PROJECT.md` §3 and Rule A state the layout rule; **this file** states the why and the aggressiveness.

---

## 4. Convention over configuration

* Follow existing patterns in the nearest sibling package before inventing a new shape.
* Prefer explicit, boring structure (named modules, clear `__all__`, services for business logic) over clever indirection.
* Views stay thin; business logic belongs in `operations/services/` (or domain helpers), not stuffed into a growing view file.
* Templates: explicit `{% include ... with ... %}` context — no magic inheritance for action endpoints (`PROJECT.md` Rule B / `platform.md`).

When in doubt, copy the **scheduling / customers / feed** package style, not a new one-off layout.

---

## 5. Import layering (avoid circular imports)

Django loads `operations/models/__init__.py` early. A **circular import** happens when a model module top-level-imports a services package that, while loading, imports that same model.

| Layer | OK at module top level | Avoid |
|-------|------------------------|--------|
| **`operations/models/*`** | Other models, Django, stdlib | **Services** — especially a package `__init__.py` that eagerly loads many submodules |
| **`operations/services/*`** | Models via **submodule paths** (`operations.models.customers`, `operations.models.scheduling`) | Relying on `from operations.models import X` when that triggers a half-loaded `models/__init__` |
| **Model method needs a service** | **Lazy import inside the method**; prefer a **leaf** module (e.g. `feed_interactions.slugs`) | Top-level `from operations.services…` |

**Why leaf imports:** `from operations.services.feed_interactions import dog_slug_from_name` still runs the package `__init__` (access, check-in poll, …). `from operations.services.feed_interactions.slugs import …` only loads slug helpers.

Do **not** “fix” cycles by restoring deleted top-level shims (`feed_slugs.py`, etc.). Fix the layering.

---

## 6. How this relates to SOC 2 posture

We are not claiming certification from file size. We are choosing habits that make compliance work possible:

* **Confidentiality / boundaries:** code units that match domain boundaries are easier to scope (and later to tenant-scope).
* **Processing integrity:** small modules with clear entry points are easier to test and harder to bypass accidentally.
* **Reviewability:** David (and reviewers) can open a file and verify claims — same standard we want for security-sensitive paths (feed visitor handling, auth walls, exports).

Product SOC 2 controls (tenant isolation targets, visitor tracking, no PII in logs) still live in `PROJECT.md` §9.1 and the domain files. Philosophy here is **how we structure code** so those controls stay enforceable.

---

## 7. Working with LLMs (standing expectations)

* Do **not** append “just one more function” into an already-large module when a split is the honest fix.
* Prefer a short package map in the domain `.md` when you add a submodule.
* After a structural split, update the matching `LLM/<domain>.md` paths so the next session does not thrash on deleted monoliths.
* Large feature work (e.g. services/pricing catalog) must start as a **domain package**, not a single god file — see `services.md` (Phase 1 catalog landed; checkout engine cutover is Phase 2).

---

## 8. What this file is not

* Not a substitute for `platform.md` (dev server, UX density, PWA).
* Not a substitute for domain rules (pricing tiers, visit guards, capacity).
* Not permission to rewrite working packages “for purity” without David asking.

When philosophy and a domain rule conflict on a product decision, **domain + David win**. When they conflict on file shape, **this philosophy wins**: keep units small and auditable.
