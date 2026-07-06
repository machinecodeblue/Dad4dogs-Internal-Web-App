# Domain: Customer Feed & Timeline

**Covers:** David's staff timeline (capture during check-in) and the **customer-facing photo feed** (read-only, no password).

**Code packages:**
- `operations/models/scheduling.py` — `TimelineMediaAsset`, `VisitTimelineEvent`
- `operations/models/customers.py` — `feed_secret`, `feed_dog_slug`, `FeedAccessLog`
- `operations/views/scheduling.py` — `visit_timeline`, `visit_timeline_forward` (staff)
- `operations/views/customer_feed.py` — `customer_feed` (public)
- `operations/views/customers.py` — `dog_feed_regenerate` (staff)

**Services:** `timeline_media.py`, `timeline_visits.py`, `geolocation.py`, `feed_slugs.py`, `feed_access.py`  
**Templates:** `visit_timeline.html` (staff), `customer_feed.html`, `customer_base.html` (public)

---

## 1. Two Audiences

| Audience | URL | Auth | Can do |
|----------|-----|------|--------|
| **David (staff)** | `/visits/<id>/timeline/` | `@login_required` | Capture photo/video, GPS, caption, forward to other checked-in dogs |
| **Customer / family** | `/feed/<secret>/<dog-slug>/` | Secret link only | View full history — photos, videos, captions, timestamps |

Admin tools (dashboard, clients, billing) stay behind Django login. Customers never get accounts or passwords.

---

## 2. Data Model (Option C — shared media)

### `TimelineMediaAsset` (immutable capture)
One file set per moment — can be linked to multiple visits when forwarded.

| Field | Purpose |
|-------|---------|
| `media_type` | `photo` or `video` |
| `photo_high_res` | Master image (customer can tap to open/print) |
| `photo_thumbnail` | WebP display thumbnail |
| `video_file` | Gallery video (max 25 MB) |
| `caption_notes` | Optional text |
| `latitude`, `longitude` | GPS or business fallback |
| `location_used_fallback`, `location_fallback_label` | When device GPS unavailable |
| `captured_at` | Exact capture time — preserved on forward |
| `original_visit` | First visit this moment was logged against |

### `VisitTimelineEvent` (link row)
Links one `TimelineMediaAsset` to one `Visit`. Forwarding creates new rows pointing at the **same** asset.

| Field | Purpose |
|-------|---------|
| `visit` | FK → `Visit` |
| `media_asset` | FK → `TimelineMediaAsset` |
| `source_event` | Set when forwarded from another dog's timeline |
| `shared_at` | When attached to this visit |

**Constraint:** unique `(visit, media_asset)` — no duplicate asset on same visit.

### Customer feed credentials (`ClientProfile`)

| Field | Purpose |
|-------|---------|
| `feed_secret` | Speakable secret slug (unique globally) |
| `feed_dog_slug` | URL segment from dog name (`Lulu` → `lulu`) |

### `FeedAccessLog`
Anonymous access tracking per browser cookie — not per person.

| Field | Purpose |
|-------|---------|
| `client` | FK → `ClientProfile` |
| `visitor_id` | UUID from cookie `dad4dogs_feed_vid` |
| `user_agent` | Truncated UA string |
| `accessed_at` | Page view timestamp |

---

## 3. Feed URL Pattern

```
/feed/squeakytiki/lulu/
      ↑ feed_secret  ↑ feed_dog_slug
```

### Speakable secret generation (`feed_slugs.py`)
- Stacked **CV syllables** (consonant + vowel): two chunks of 2–3 syllables → `movakitu`, `bokomelu`
- Scale: ~8 dogs, ~30 customers — guessability is not a concern at this size
- **Uniqueness:** DB unique on `feed_secret`; retry on collision; UUID hex as last resort
- **Regenerate:** `dog_feed_regenerate` issues new `feed_secret` only — old shared links stop working

### Methods on `ClientProfile`
- `ensure_feed_credentials()` — lazy-create secret + slug
- `feed_url_path()`, `feed_url(request=None)` — path or absolute URL
- `regenerate_feed_secret()` — unshare / revoke old links
- `sync_feed_dog_slug()` — align slug when dog name edited

### Environment
`PUBLIC_SITE_URL` in `config/settings.py` — base URL for feed links in booking emails (e.g. ngrok tunnel).  
Without it, emails omit the absolute URL; dog detail still shows full URL when browsed.

---

## 4. Staff Timeline (capture)

### Eligibility
- Only while visit status is **`checked_in`** (`Visit.accepts_timeline_events`)
- Forward targets: **other currently checked-in visits** only (`timeline_visits.active_checked_in_visits`)
- Checkout removes dog from forward list

### Capture UX (`visit_timeline.html`)
- Camera photo, gallery photo, or gallery video
- GPS via browser geolocation; fallback to `BUSINESS_FALLBACK_LATITUDE/LONGITUDE` from settings
- Multi-dog checkbox when multiple dogs checked in
- Forward form per event → other checked-in dogs

### Entry point
Mobile check-in card → **Log Moment** → `/visits/<pk>/timeline/`

### Key service functions (`timeline_media.py`)
`log_moment_for_visits`, `create_photo_asset`, `create_video_asset`, `forward_timeline_event`, `visits_available_for_forward`

---

## 5. Customer Feed (interactive, secret-link auth)

### URL routes
| Path | View | Auth |
|------|------|------|
| `/feed/<feed_secret>/<feed_dog_slug>/` | `customer_feed` | Public (secret link) |
| `/feed/<feed_secret>/` | `customer_feed_redirect` | Redirects to canonical two-part URL |

### What customers see
- All timeline events for that dog, newest first (full history across visits)
- Thumbnail photos (tap → full-res), videos with controls
- Caption and capture time
- **Emoji reactions** (👍 ❤️ 😂 😮 😢) — one per browser via `visitor_id` cookie
- **Comments** — optional display name (stored in cookie), chronological thread
- **Share this moment** — creates UUID link; does **not** expose feed URL
- “Group moment” badge on forwarded events — **no** raw GPS, admin nav, or capture controls

### What customers do **not** see
- Other dogs' feeds, billing, pipeline, COI
- Internal ops notes unless written in `caption_notes`

### Interaction models (`scheduling.py`) — **not** Django `User`
Customers have no accounts. Use `visitor_id` cookie (`dad4dogs_feed_vid`), not `User` FK.

| Model | Purpose |
|-------|---------|
| `MediaReaction` | One emoji per visitor per `TimelineMediaAsset` |
| `MediaComment` | Text + `display_name` per visitor |
| `SharedMediaLink` | UUID pk → single moment public landing page |

Service: `operations/services/feed_interactions.py`

### Public single-moment share
| Path | Purpose |
|------|---------|
| `/feed/share/<token>/` | Anonymous — one image/video + dog name + “Powered by Dad4dogs” (e.g. `eXIvE692WTJul1JvM`) |

Does not reveal `/feed/<secret>/<dog>/`. UUID is unguessable (128-bit).

### Interaction POST routes (CSRF-protected forms)
| Path | Action |
|------|--------|
| `.../moment/<asset_id>/react/` | Set or clear emoji |
| `.../moment/<asset_id>/comment/` | Post comment (30/day per visitor rate limit) |
| Share icon (per moment) | Bottom sheet: Copy link, Gmail, WhatsApp, Facebook, native Share |

### Response headers
- `X-Robots-Tag: noindex, nofollow`
- `Cache-Control: private, no-store`

### Staff management (dog detail `/dogs/<id>/`)
- Full feed URL with **Copy Link** and **Open Feed**
- 30-day stats: page views + distinct browser IDs (cookie)
- **Regenerate Link** — confirm dialog; revokes old secret

### Booking email
When `PUBLIC_SITE_URL` is set, `format_booking_confirmation()` appends the feed URL so customers can bookmark on first booking.

---

## 6. Security Model (David's scale)

| Principle | Detail |
|-----------|--------|
| No passwords | Possession of URL = access (capability URL) |
| Low scale | ~8 dogs, ~30 customers — speakable slugs are fine |
| Revocation | Regenerate `feed_secret` on dog detail |
| Sharing intentional | Customers forward link to family — by design |
| Staff vs public | Never expose upload/forward on customer template |

**Not yet built:** protected media proxy for production (dev serves `/media/` in DEBUG).  
**Future:** hearts, comments, emojis, push notifications — visitor cookie is the hook for per-browser reactions without login.

---

## 7. Views & URLs Summary

| Path | Name | Login |
|------|------|-------|
| `/visits/<pk>/timeline/` | `visit_timeline` | Yes |
| `/visits/<pk>/timeline/<event_pk>/forward/` | `visit_timeline_forward` | Yes |
| `/feed/<secret>/<dog-slug>/` | `customer_feed` | No |
| `/feed/.../moment/<asset_id>/react/` | `customer_feed_react` | No (POST) |
| `/feed/.../moment/<asset_id>/comment/` | `customer_feed_comment` | No (POST) |
| `/feed/.../moment/<asset_id>/share/` | `customer_feed_share` | No (POST) |
| `/feed/share/<token>/` | `public_feed_share` | No |
| `/dogs/<pk>/feed/regenerate/` | `dog_feed_regenerate` | Yes (POST) |

---

## 8. Tests

`TimelineTests`, `FeedSlugTests`, `CustomerFeedTests`, `FeedInteractionTests` in `operations/tests.py`.  
`VisitEmailTests.test_format_confirmation_includes_feed_url_when_public_site_set`

---

## 9. Migrations

| Migration | Contents |
|-----------|----------|
| `0008_visit_timeline_event` | Initial timeline (later refactored) |
| `0009_timeline_media_asset` | `TimelineMediaAsset` + data migration |
| `0010_customer_feed` | `feed_secret`, `feed_dog_slug`, `FeedAccessLog` |
| `0011_feed_interactions` | `MediaReaction`, `MediaComment`, `SharedMediaLink` |

---

## 10. Not Yet Built

| Item | Notes |
|------|-------|
| Push notifications | “New photo!” → tap feed link; needs stable domain + web push |
| Comment moderation queue | David approves/hides comments — not needed at current scale |
| `published` flag per moment | David approves before customer sees — not needed today |
| Production media auth | Proxy or signed URLs so `/media/` is not wide open |

## 11. Architectural payoff — two circles, zero data bleed

### Interactive client circle (owner ↔ David)
- Customers react and comment on **`/feed/<secret>/<dog>/`** using the anonymous **`dad4dogs_feed_vid`** cookie — not Django `sessionid`, not accounts.
- David sees activity on **Check-In** (`/checkin/`) via a lightweight **15s JSON poll** (`/checkin/feed-activity/`, `@login_required`).
- Poll uses David’s **session cookie** only on the staff side — comments stay between owner/family and David’s ops screen.

### Secure virality (friends ↔ marketing)
- **Share with friends** creates `SharedMediaLink` (UUID).
- Public view: `/share/photo/<uuid>/` → template `public_photo_share.html` — **only** the moment + dog’s first name + “Powered by Dad4dogs”.
- No feed URL, no owner email, no billing, no account IDs — organic word-of-mouth without privacy compromise.
- `view_count` increments per public page view (owner fun metric).

```python
# public_shared_media view
record_share_view(link)
return render(request, 'operations/public_photo_share.html', {
    'photo': link.media_asset,
    'dog_name': link.client.dog_name,
})
```

---

## 12. Design note — adapting generic “social login” patterns

Third-party designs often use `User` FK and “strict authentication” on the feed. **Dad4dogs does not:**

| Generic proposal | Dad4dogs choice |
|------------------|-----------------|
| `TimelineEventPhoto` | `TimelineMediaAsset` + `VisitTimelineEvent` |
| Django `User` on reactions | `visitor_id` cookie — no customer passwords |
| Login required on `/feed/...` | Secret speakable URL (capability link) |
| Sequential photo IDs | UUID `SharedMediaLink` for public single-moment share |