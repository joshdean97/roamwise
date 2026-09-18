# LeavePrints content API

The content API supplies reel-ready public trips to Make and records which
trips have already been posted. It uses a dedicated bearer token rather than a
browser session.

## Configuration

Generate a long random secret, set it as `CONTENT_API_KEY` in the production
environment, and deploy the database migration.

Every request must include:

```http
Authorization: Bearer YOUR_CONTENT_API_KEY
```

## Get unused trips

```http
GET /api/admin/content/trips?limit=5&unused=true&platform=instagram&format=trial_reel
```

Only public trips with at least one destination are returned. `limit` defaults
to 5 and may be between 1 and 20. `unused` is scoped to the selected platform
and format.

```json
{
  "trips": [
    {
      "id": 142,
      "title": "A week in Italy",
      "route": "Rome → Florence → Bologna",
      "destination_names": ["Rome", "Florence", "Bologna"],
      "destinations": [
        {
          "city": "Rome",
          "country": "Italy",
          "country_code": "IT",
          "nights": 2,
          "accommodation": 48.0,
          "living": 36.0,
          "total": 84.0
        }
      ],
      "legs": [
        {
          "from_city": "Rome",
          "to_city": "Florence",
          "mode": "train",
          "cost": 28.0
        }
      ],
      "days": 7,
      "nights": 7,
      "currency": "GBP",
      "currency_symbol": "£",
      "costs": {
        "accommodation": 168.0,
        "living": 126.0,
        "transport": 73.0,
        "stay": 294.0,
        "total": 367.0,
        "per_day": 52.43
      },
      "reel": {
        "headline": "7 days across Rome → Florence → Bologna for £367",
        "route": "Rome → Florence → Bologna",
        "budget_label": "£367 total",
        "per_day_label": "£52 per day",
        "overlay_text": "I planned my travel costs with this website…\n\n🇮🇹 Rome — 2 days: £84\n🚆 Rome → Florence: £28\n…",
        "caption": "I planned 7 days across Rome → Florence → Bologna for £367 — £52 per day.\n…",
        "status": "draft"
      },
      "share_url": "https://leaveprints.com/share/opaque-token"
    }
  ],
  "meta": {
    "count": 1,
    "limit": 5,
    "unused_only": true,
    "platform": "instagram",
    "format": "trial_reel"
  }
}
```

## Record a posted reel

Call this after the reel has successfully been created or posted:

```http
POST /api/admin/content/trips/142/used
Content-Type: application/json

{
  "platform": "instagram",
  "format": "trial_reel",
  "hook": "A week in Italy for under £400",
  "posted_at": "2026-09-18T08:30:00Z",
  "external_media_id": "optional-instagram-media-id"
}
```

`posted_at` defaults to the current time. The other optional tracking fields
can be omitted. After this succeeds, the trip is excluded from future
`unused=true` requests for the same platform and format.
