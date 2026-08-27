# Decision

- **Status:** accepted (pattern) / rejected (restore eed_slugs.py)
- **Live spec:** LLM/applicationphilosophy.md (Import layering); LLM/feed.md (leaf imports for slug helpers from models)
- **What we took:** Models must not top-level-import services; lazy import inside model methods; prefer leaf modules (eed_interactions.slugs) over package __init__; services prefer operations.models.customers / .scheduling over package-root operations.models
- **What we left:** Restoring top-level eed_slugs.py (superseded by consolidated package; no shims)
- **Why:** The analysis correctly diagnosed the cycle; the suggested path was outdated after feed helper consolidation

---

This is a classic Python **circular import** triggered during Django app initialization.

---

### The Import Loop

1. Django starts loading models via `operations/models/__init__.py`.


2. `operations/models/billing.py` loads `operations/models/customers.py` (`ClientProfile`).


3. `operations/models/customers.py` (line 14) executes a top-level import:
```python
from operations.services.feed_interactions import dog_slug_from_name, generate_unique_feed_secret

```


4. `feed_interactions/__init__.py` loads `feed_interactions/access.py`.


5. `feed_interactions/access.py` tries to import `ClientProfile` from `operations.models.customers`.


6. **Failure:** Python cannot import `ClientProfile` because `customers.py` is paused at line 14 waiting for `feed_interactions` to finish loading.

---

### The Root Cause

`dog_slug_from_name` and `generate_unique_feed_secret` are slug generation utilities that originally lived in `operations/services/feed_slugs.py`.

When importing them from `feed_interactions` at the top level of `customers.py`, you pulled in the entire `feed_interactions` package (which imports models at module load time).

---

### The Fix (2 Quick Steps)

#### 1. Fix the Import in `operations/models/customers.py`

Change line 14 in `operations/models/customers.py` to import directly from `feed_slugs.py` (which has no circular dependencies):

```python
# operations/models/customers.py (around line 14)
# ❌ Remove this:
# from operations.services.feed_interactions import dog_slug_from_name, generate_unique_feed_secret

# ✅ Replace with this:
from operations.services.feed_slugs import dog_slug_from_name, generate_unique_feed_secret

```

#### 2. Verify `operations/services/feed_slugs.py`

Ensure `operations/services/feed_slugs.py` does **not** import `ClientProfile` or `SharedMediaLink` at the module top level. If it queries the DB to check uniqueness, keep the import localized inside the function:

```python
# operations/services/feed_slugs.py

def generate_unique_feed_secret(*, max_attempts: int = 40) -> str:
    # Local import prevents circular loading when models import this module
    from operations.models.customers import ClientProfile

    for _ in range(max_attempts):
        candidate = generate_feed_secret()
        if not ClientProfile.objects.filter(feed_secret=candidate).exists():
            return candidate
    return uuid.uuid4().hex

```

Once you point line 14 of `customers.py` back to `feed_slugs.py`, Django's reloader will boot cleanly.