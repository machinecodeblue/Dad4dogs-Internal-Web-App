> **Next major build — design basis, not live code.**  
> This file is the standing design for the upcoming **business services + configurable pricing** work (service catalog, rates, non-dog offerings, behavior rules). There is **no** `operations/models/services.py` (or matching forms/views) yet.  
> **Live pricing today** remains the hardcoded tiers in `scheduling.md` / `operations/pricing.py`.  
> **Do not implement from this file** until David explicitly starts the services build (he may finish package refactoring first). When that build starts, ship it as a **domain package** (models/forms/views/services split early) per `applicationphilosophy.md` — not a single god module. Pattern to copy: `views/scheduling/`, `views/customers/`, `views/feed/`.

### Domain: Services & Offerings

**Covers:** Dynamic business services, customizable rates, home/pet drop-in checks, and billing engine calculations.

**Intended code packages (when built):** `operations/models/services.py` (or `models/services/` package), `forms/services.py`, `views/services/` package with `__init__.py` re-exports — exact split follows `applicationphilosophy.md`.

### 1. Purpose

Operators need the flexibility to manage their business catalog without modifying source code. The application must support diverse service profiles—ranging from standard dog boarding to property care and drop-in visits for non-canine pets (cats, guinea pigs, rabbits)—complete with custom tier rules and independent rate structures managed through /settings/services/. 

### 2. Data Model

### BusinessService

Defines an active commercial offering available for a tenant's business. 

Field 

Type 

Purpose 

**name**
CharFieldPublic name (e.g., "Standard Overnight Stay", "House & Small Pet Check")
**slug**
SlugFieldCode identifier for pricing engine lookup (overnight_stay, house_check)
**target_category**
CharField (Choices)DOG, CAT, SMALL_PET, PROPERTY_ONLY
**rate_type**
CharField (Choices)FLAT, HOURLY, DAILY
**base_rate**
DecimalFieldNumeric fee applied per unit in CAD
**is_active**
BooleanFieldControls visibility on booking drop-downs; soft-deletes only
**capacity_exempt**
BooleanFieldIf True, bookings bypass facility standard/insurance ceiling limits

### ServiceBehaviorRule

Optional conditional rules mapped to a service to handle tier switches (e.g., changing rates based on duration thresholds). 

Field 

Type 

Purpose 

**service**
FK → BusinessServiceThe parent service receiving the modifier
**trigger_type**
CharField (Choices)DURATION_UNDER, DURATION_OVER, TIME_WINDOW
**threshold_value**
IntegerFieldHour count or time parameter triggering the rule
**modified_rate**
DecimalFieldThe new rate applied if the condition evaluates to True

### 3. Operational Logic & Interface Rules

### The Drop-In Validation Model

* When David or another operator books a service where target_category is not DOG, or capacity_exempt is set to True, the system bypasses the same-day facility capacity checks.
* House checks and small pet visits can scale infinitely on a busy holiday weekend without blocking standard high-margin dog stays.

### Pricing Evaluation Flow

1. David selects a ClientProfile and links a BusinessService to a new booking window.
2. At checkout, pricing.py reads the recorded BusinessService and loops through its active ServiceBehaviorRule dependencies.
3. If an overnight window rule is triggered (e.g., a time-sensitive window boundary crossing), the modified rate is logged into fee_breakdown JSON fields dynamically.