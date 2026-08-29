# Decision: HTML monolith file review

**Status:** accepted (conventions + phased splits)  
**Live spec:** `LLM/domains/platform.md` § Template packages; components under `operations/templates/operations/components/`  
**What we took:** `components/` tree for product UI; keep `includes/` for chrome/feed social; timeline then visit form; partials before static CSS/JS.  
**What we left:** Full redesign of badges; forcing staff/customer moment cards to share one partial; splitting every sub-10KB template.  
**Why:** Match Python packaging — small, auditable UI units and consistent chrome.

---

That audit table shows the next round of architectural drift. While Python backend services, models, and forms were modularized, **frontend templates (`visit_form.html` at 17.3 KB and `visit_timeline.html` at 12.6 KB)** have grown into monolithic HTML files.

In Django applications with dynamic mobile forms and staff timelines, templates inflate because they inline:

1. **Media/Moment Cards:** Photo/video cards, geolocation badges, forward triggers, and visitor comment streams.


2. **Form Layout Blocks:** Natural-language start/end parsing feedback, capacity warning alerts, and repeat occurrence generators.


3. **Embedded Script/Styles:** Inline vanilla JS for datetime blur parsing, coordinate extraction, or polling loops.



---

### Componentization Strategy (`{% include ... with ... %}`)

Following `PHILOSOPHY.md` §4 (explicit template context, no magic inheritance), decompose these large templates into reusable components under `operations/templates/operations/components/`:

#### 1. Decomposing `visit_timeline.html` (12.6 KB)

```
operations/templates/operations/
├── visit_timeline.html                     # Lean outer shell (header, back link, feed status)
└── components/
    ├── timeline/
    │   ├── capture_form.html               # File inputs (camera/gallery/video) & GPS hidden fields
    │   ├── moment_card.html                # Shared media card (photo thumbnail, video player, timestamp, GPS)
    │   ├── forward_modal.html              # Multi-dog share picker and forward submission
    │   └── interaction_feed.html           # Comments, emoji reactions, and visitor metadata

```

* **Reuse Win:** `moment_card.html` and `interaction_feed.html` can be shared between the staff check-in timeline (`visit_timeline.html`) and the customer-facing social feed (`customer_feed.html` / `shared_moment.html`).



#### 2. Decomposing `visit_form.html` (17.3 KB)

```
operations/templates/operations/
├── visit_form.html                         # Form wrapper, submit buttons, delete trigger
└── components/
    ├── scheduling/
    │   ├── datetime_parse_preview.html     # Natural language input + parse preview card
    │   ├── repeat_rules_panel.html         # Frequency, interval, until-date inputs
    │   ├── capacity_banner.html            # Daily limit / warning alert banner
    │   └── service_pricing_summary.html    # Selected BusinessService rate & billing estimate

```

* **Reuse Win:** `capacity_banner.html` and `datetime_parse_preview.html` can be reused directly on intake wizard flows (`client_intake.html`) and quick schedule modals.



---


Splitting `visit_timeline.html` or `visit_form.html` into component partials will keep individual template sizes manageable and enable reuse across customer and admin views.

Tackling template componentization now delivers immediate value across UX consistency, auditability, and token footprint.

When admin templates share canonical components:

* **UI Inconsistencies Disappear:** A capacity alert, address preview, or dog summary card looks, behaves, and formats identical data whether you are on the Dashboard, Check-in, Intake Wizard, or Visit Edit form.


* **Testing & Debugging Simplifies:** Template rendering bugs are isolated to a single component template rather than duplicated across 500 lines of disparate HTML.


* **Explicit Parameter Contracts:** Following `PHILOSOPHY.md` §4 with `{% include "operations/components/...html" with form=form ... %}` eliminates hidden scope leaks and makes every component’s required input data obvious at a glance.



Which template would you like to inspect and extract components from first—`visit_form.html` (scheduling inputs/capacity alerts) or `visit_timeline.html` (media moments/forwarding)?