# Domain: Customer Feed & Timeline

**Covers:** David's staff timeline (capture during check-in) and the **customer-facing photo feed** (read-only, no password).

**Code packages:**
- `operations/models/scheduling.py` — `TimelineMediaAsset`, `VisitTimelineEvent`
- `operations/models/customers.py` — `feed_secret`, `feed_dog_slug`, `FeedAccessLog`
- `operations/views/scheduling.py` — `visit_timeline`, `visit_timeline_forward` (staff)
- `operations/views/customer_feed.py` — `customer_feed` (public)
- `operations/views/customers.py` — `dog_feed_regenerate` (staff)

**Services:** `timeline_media.py`, `timeline_visits.py`, `geolocation.py`, `feed_slugs.py`, `feed_access.py`, `feed_interactions.py`, `feed_emojis.py`, `share_preview.py`  
**Templates:** `visit_timeline.html` (staff), `customer_feed.html`, `public_photo_share.html`, `customer_base.html` (public)  
**Includes:** `includes/moment_interactions.html`, `moment_social_styles.html`, `share_sheet.html`, `share_sheet_script.html`, `comment_panel_script.html`

---

## 1. Two Audiences

| Audience | URL | Auth | Can do |
|----------|-----|------|--------|
| **David (staff)** | `/visits/<id>/timeline/` | `@login_required` | Capture photo/video, GPS, caption, forward to other checked-in dogs |
| **Customer / family** | `/feed/<secret>/<dog-slug>/` | Secret link only | View full history; react, comment, share individual moments |
| **Friend / public** | `/feed/share/<token>/` | Unguessable share token | View one moment; react, comment, re-share, download photo |

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
- **Dog-themed reactions** in the bar (🐾 🐕 🐶 🦴 🥺) — stored by key; **standard emojis** (👍 ❤️ …) in counts/shared text (`feed_emojis.py`)
- **Comments** — 💬 icon + count; thread/form hidden until tapped
- **Share** — compact share icon → sheet (Copy, Gmail, WhatsApp, Facebook, native)
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
| `SharedMediaLink` | UUID pk + `share_token` (16-char URL key) → public single-moment page |

Service: `operations/services/feed_interactions.py`

### Social UX (private feed + public share)

Both surfaces use the same low-friction interaction pattern via `moment_interactions.html`:

| Element | Behaviour |
|---------|-----------|
| **Reaction bar** | Always visible — dog emojis (🐾 🐕 🐶 🦴 🥺) submit on tap; **no comment required** |
| **Reaction counts** | Standard emojis (👍 ❤️ …) in summary text — `feed_emojis.py` |
| **💬 Comment balloon** | Compact icon + count badge; thread/form **hidden until tapped** |
| **Share icon** | Compact icon → bottom sheet (Copy, Gmail, WhatsApp, Facebook, native `navigator.share`) |
| **Download icon** | Public share page only — saves high-res file as `dad4dogs_<uuid>.jpg` |

Share URLs are stripped of `?` and `#` before copying/sharing.

### Private feed POST routes (CSRF-protected forms)
| Path | Action |
|------|--------|
| `/feed/<secret>/<dog>/moment/<asset_id>/react/` | Set or clear emoji |
| `/feed/<secret>/<dog>/moment/<asset_id>/comment/` | Post comment (30/day per visitor rate limit) |

Share icon opens bottom sheet — no POST; uses existing `SharedMediaLink.share_token`.

### Public single-moment share

| Path | Purpose |
|------|---------|
| `/feed/share/<token>/` | One image/video + full social UX (react, comment balloon, re-share, download) |
| `/feed/share/<token>/react/` | POST — set or clear emoji |
| `/feed/share/<token>/comment/` | POST — post comment |
| `/feed/share/<token>/download/` | GET — `FileResponse` with `Content-Disposition: attachment; filename="dad4dogs_<uuid>.jpg"` |
| `/share/photo/<uuid>/` | Legacy redirect → `/feed/share/<token>/` |

- **URL token:** `share_token` — 16-char alphanumeric (e.g. `eXIvE692WTJul1JvM`), not the UUID in the path
- **Download filename:** `dad4dogs_{SharedMediaLink.id}.jpg` (or `.mp4` for video) — served via download endpoint so browsers do not use internal `master_…` storage names
- Does **not** reveal `/feed/<secret>/<dog>/`
- **View counting:** `view_count` increments on GET only; POST redirects use `?posted=1` to skip re-counting
- **Robots:** `index, follow` on share page (OG crawlers); private feed stays `noindex, nofollow`

**Social previews:** `share_preview.py` sets Open Graph + Twitter tags with the **moment photo** as `og:image` (not the Dad4dogs app icon). High-res image URL used for `og:image`, `twitter:image`, and page favicon.

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

**Built:** reactions, comments, public share with re-share, download, check-in activity poll.  
**Not yet built:** protected media proxy for production (dev serves `/media/` in DEBUG).

---

## 7. Views & URLs Summary

| Path | Name | Login |
|------|------|-------|
| `/visits/<pk>/timeline/` | `visit_timeline` | Yes |
| `/visits/<pk>/timeline/<event_pk>/forward/` | `visit_timeline_forward` | Yes |
| `/checkin/feed-activity/` | `checkin_feed_activity` | Yes (JSON poll) |
| `/feed/<secret>/<dog-slug>/` | `customer_feed` | No |
| `/feed/<secret>/<dog-slug>/moment/<asset_id>/react/` | `customer_feed_react` | No (POST) |
| `/feed/<secret>/<dog-slug>/moment/<asset_id>/comment/` | `customer_feed_comment` | No (POST) |
| `/feed/share/<token>/` | `public_feed_share` | No |
| `/feed/share/<token>/react/` | `public_feed_share_react` | No (POST) |
| `/feed/share/<token>/comment/` | `public_feed_share_comment` | No (POST) |
| `/feed/share/<token>/download/` | `public_feed_share_download` | No |
| `/share/photo/<uuid>/` | `public_shared_media_legacy` | No (redirect) |
| `/dogs/<pk>/feed/regenerate/` | `dog_feed_regenerate` | Yes (POST) |

---

## 8. Tests

`TimelineTests`, `FeedSlugTests`, `CustomerFeedTests`, `FeedInteractionTests` in `operations/tests.py`.

`FeedInteractionTests` covers: feed react/comment, public share isolation from feed secret, compact share/comment icons, public share react without comment, public share download filename (`dad4dogs_<uuid>.jpg`), check-in feed activity poll.

`VisitEmailTests.test_format_confirmation_includes_feed_url_when_public_site_set`

---

## 9. Migrations

| Migration | Contents |
|-----------|----------|
| `0008_visit_timeline_event` | Initial timeline (later refactored) |
| `0009_timeline_media_asset` | `TimelineMediaAsset` + data migration |
| `0010_customer_feed` | `feed_secret`, `feed_dog_slug`, `FeedAccessLog` |
| `0011_feed_interactions` | `MediaReaction`, `MediaComment`, `SharedMediaLink` |
| `0012_shared_media_share_token` | `SharedMediaLink.share_token` for clean public URLs |
| `0013_…` | Index rename on interaction models |

---

## 10. Not Yet Built

| Item | Notes |
|------|-------|
| Push notifications | “New photo!” → tap feed link; needs stable domain + web push |
| Comment moderation queue | David approves/hides comments — not needed at current scale |
| `published` flag per moment | David approves before customer sees — not needed today |
| Production media auth | Proxy or signed URLs so `/media/` is not wide open |
| Feed template refactor | `customer_feed.html` could adopt shared includes (currently inline; share page uses includes) |

## 11. Architectural payoff — two circles, zero data bleed

### Interactive client circle (owner ↔ David)
- Customers react and comment on **`/feed/<secret>/<dog>/`** using the anonymous **`dad4dogs_feed_vid`** cookie — not Django `sessionid`, not accounts.
- Optional display name stored in cookie `dad4dogs_feed_name` for comment attribution.
- David sees activity on **Check-In** (`/checkin/`) via a lightweight **15s JSON poll** (`/checkin/feed-activity/`, `@login_required`).
- Poll uses David’s **session cookie** only on the staff side — reactions/comments appear on the check-in screen with standard emoji labels.

### Secure virality (friends ↔ marketing)
- **Share with friends** lazily creates `SharedMediaLink` per `(client, media_asset)` with `share_token`.
- Public landing: **`/feed/share/<token>/`** → `public_photo_share.html` — moment + dog name + **same social UX** (react without commenting, comment balloon, re-share, download).
- Legacy `/share/photo/<uuid>/` redirects to token URL.
- No feed secret, no owner email, no billing — organic word-of-mouth without privacy compromise.
- `view_count` increments on share page GET (not on interaction POST redirects).

```python
# public_feed_share (simplified)
link = _resolve_share_link(share_token)
if request.GET.get('posted') != '1':
    record_share_view(link)
return render(request, 'operations/public_photo_share.html', _share_page_context(...))

# public_feed_share_download
filename = f'dad4dogs_{link.id}.jpg'  # SharedMediaLink UUID pk
return FileResponse(field.open('rb'), as_attachment=True, filename=filename)
```

### Key implementation files
| Area | Path |
|------|------|
| Views | `operations/views/customer_feed.py` — feed, share, react, comment, download |
| Interactions | `operations/services/feed_interactions.py` — reactions, comments, share links, view count |
| OG + download | `operations/services/share_preview.py` — preview image, download filename/URL |
| Emojis | `operations/services/feed_emojis.py` — dog UI emojis vs standard count labels |
| Staff poll | `operations/views/scheduling.py` — `checkin_feed_activity` |

---

## 12. Design note — adapting generic “social login” patterns

Third-party designs often use `User` FK and “strict authentication” on the feed. **Dad4dogs does not:**

| Generic proposal | Dad4dogs choice |
|------------------|-----------------|
| `TimelineEventPhoto` | `TimelineMediaAsset` + `VisitTimelineEvent` |
| Django `User` on reactions | `visitor_id` cookie — no customer passwords |
| Login required on `/feed/...` | Secret speakable URL (capability link) |
| Sequential photo IDs | UUID `SharedMediaLink` for public single-moment share |