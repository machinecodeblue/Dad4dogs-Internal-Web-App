# Decision

- **Status:** accepted (partial)
- **Live spec:** LLM/feed.md (dual audience + 	imeline_media/ / eed_interactions/ package maps); PROJECT.md services tree
- **What we took:** Dual-purpose framing (client engagement vs contemporaneous audit); Phase 1 split of fat service modules into packages
- **What we left:** Extracting timeline models from models/scheduling.py (future Phase 2)
- **Why:** Keep feed/timeline maintainable under applicationphilosophy without changing product behavior

---

Your understanding captures the dual purpose of this architecture: **client delight on the front end** and an **immutable, contemporaneous evidentiary audit trail on the backend**.

---

### How the Two Audiences Map to Your Stack

```
                     ┌──────────────────────────────────────────────┐
                     │         Staff Capture (Contemporaneous)      │
                     │  • /visits/<id>/timeline/                    │[cite: 6]
                     │  • @login_required (David's phone)           │[cite: 6]
                     │  • Direct GPS coordinates / Fallback label   │[cite: 6, 16]
                     │  • Exact capture timestamp                   │[cite: 6, 16]
                     └──────────────────────┬───────────────────────┘
                                            │
                                            ▼
                             ┌──────────────────────────────┐
                             │      TimelineMediaAsset      │
                             │  (Immutable On-Disk Capture) │[cite: 6]
                             └──────┬────────────────┬──────┘
                                    │                │
            ┌───────────────────────┘                └────────────────────────┐
            ▼                                                                 ▼
┌───────────────────────────────────────┐                 ┌───────────────────────────────────────┐
│     Purpose 1: Client Engagement      │                 │  Purpose 2: Evidentiary & Compliance  │
│                                       │                 │                                       │
│ • Private feed (/feed/<secret>/<dog>/)│[cite: 6]       │ • Exact Door Times: Check-in/out timestamps[cite: 8, 9]
│ • Dog reaction bar (🐾 🐕 🐶 🦴 🥺)   │[cite: 6, 13]   │ • Contemporaneous capture logs (GPS + time)[cite: 6, 16]
│ • Family comments & public single-    │[cite: 6, 14]   │ • COI paper audit & vet emergency caps│[cite: 4, 5]
│   moment token share (/feed/share/...)│[cite: 6, 14]   │ • Zero cross-dog data bleed (SOC 2)   │[cite: 6, 8]
└───────────────────────────────────────┘                 └───────────────────────────────────────┘

```

---

### 1. Client Engagement & Viral Growth (The Public Surface)

* **Zero-Friction Access:** Capability URLs (`/feed/<secret>/<dog>/`) allow pet owners and their immediate families to follow the day without creating accounts, remembering passwords, or installing apps.


* **Low-Friction Social UX:** The dog-themed reaction bar (`🐾`, `🐕`, `🐶`, `🦴`, `🥺`) and pop-up comment threads let clients interact in real time. You can monitor this activity directly from the mobile check-in dashboard via the lightweight 15-second activity poll (`/checkin/feed-activity/`).


* **Controlled Virality:** When an owner taps **Share**, the app generates a single-moment public link (`/feed/share/<token>/`). Friends and extended family can view, react, download, or re-share that single photo with Open Graph preview cards without gaining access to the dog's full private visit history, billing data, or home address.



---

### 2. The Contemporaneous Audit Trail (The Defensive Surface)

From an insurance, municipal compliance, and SOC 2 perspective, post-incident recollections carry little legal weight compared to contemporaneous, system-timestamped operational logs:

* **Location & Time Stamping:** When you capture a photo or video via `/visits/<id>/timeline/`, `create_photo_asset` and `create_video_asset` write `captured_at = timezone.now()` alongside precise browser GPS coordinates (`latitude`, `longitude`) or a recorded business fallback label.


* **Immutable State Transitions:** A visit must be actively `checked_in` to accept timeline moments (`Visit.accepts_timeline_events`). Transition timestamps (`actual_arrival`, `actual_departure`) cannot be casually manipulated or double-tapped without passing explicit model transition guards.


* **Group Play Documentation:** When forwarding group moments across checked-in dogs (`forward_timeline_event`), the underlying `TimelineMediaAsset` file remains a single immutable record on disk, linked via `VisitTimelineEvent` rows. If an incident or injury occurs during group play, you have photographic proof of pack dynamics, demeanor, and exact supervision times throughout the visit.



---

### Current Service Organization

The files you referenced are cleanly segmented by responsibility:

| File | Exact Job |
| --- | --- |
| `feed_access.py` | Cookie visitor tracking (`dad4dogs_feed_vid`) and 30-day distinct view/device analytics.

 |
| `feed_emojis.py` | Glyph translations: dog-themed emojis for in-feed interactions vs. standard unicode emojis for notifications and shared counts.

 |
| `feed_interactions.py` | Business logic for reactions, rate-limited comments, public share token generation, and check-in poll payloads.

 |
| `feed_slugs.py` | Cryptographic generation of pronounceable CV syllables (`squeakytiki`, `bokomelu`) and 16-character public share tokens.

 |
| `timeline_media.py` | Image normalization, WebP thumbnail generation, video file-size validation, and multi-visit event attachment.

 |
| `timeline_visits.py` | Query filters to isolate only dogs that are actively checked in for the day's timeline forwarding.

 |