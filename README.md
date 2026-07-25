# PanSou Python

FastAPI service for searching cloud-drive resources from Telegram channels and plugins. This fork is moving toward a click-time Quark transfer flow: users receive an internal open link, and the backend transfers the original Quark share into the owner drive before returning an owner-generated share link.

**Live site:** [https://panss.dpdns.org/](https://panss.dpdns.org/)

## Current Flow

- `/api/search` searches local SQLite first, then Telegram/plugin sources.
- Valid Quark links are stored in `resources`.
- When `QUARK_CLICK_TRANSFER=true`, search responses expose `/r/{resource_id}` open links instead of raw third-party Quark URLs.
- `/api/resources/{resource_id}/open` records a click and queues a transfer job.
- `/r/{resource_id}` is a browser-friendly redirect/waiting endpoint.
- `web_fallback` expands recall by searching indexed resource pages and extracting Quark links when Telegram sources miss.
- `pansou_py/core/quark.py` has a Phase 2 mock transfer client by default. Real Quark web API support is intentionally isolated for a later phase.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

Open `http://localhost:8888`.

## Important Environment Variables

- `PUBLIC_BASE_URL`: public base URL used in WeChat replies and search responses, for example `https://example.com`.
- `QUARK_CLICK_TRANSFER`: when `true`, hide original source links and return internal open links.
- `QUARK_MOCK_TRANSFER`: when `true`, generate deterministic mock Quark share links for local testing.
- `QUARK_COOKIE`: owner Quark cookie. Do not commit a real value.
- `QUARK_SAVE_FOLDER_ID`: owner folder fid for saved files. Empty saves to root.
- `QUARK_SHARE_EXPIRE_DAYS`: generated owner-share expiry. `0` requests a permanent share.
- `QUARK_SHARE_PASSWORD`: optional password for generated owner shares.
- `AUTH_ENABLED`: enables bearer-token auth for protected API/admin endpoints.
- `WECHAT_TOKEN`: enables WeChat official account webhook verification.
- `DATABASE_PATH`: SQLite database path.

## Useful Endpoints

- `GET /api/health`
- `GET /api/search?kw=keyword&res=all`
- `POST /api/search`
- `POST /api/resources/{resource_id}/open`
- `POST /api/resources/{resource_id}/open?wait=true`
- `GET /r/{resource_id}`
- `GET /api/admin/stats`
- `POST /wechat`

## Tests

```bash
pytest
```

## Search Benchmark

Measure Quark search hit rate against the built-in popular keyword set:

```bash
python scripts/search_benchmark.py --refresh --clear-cache --timeout 8 --max-pages 6 --max-results 8 --concurrency 3
```

The benchmark reports `success_rate`, misses, per-keyword link counts, and elapsed time.

## Real Quark Transfer

Local mock transfer is enabled by default. To test real save-and-reshare:

```bash
QUARK_MOCK_TRANSFER=false
QUARK_COOKIE='your-owner-quark-cookie'
QUARK_SAVE_FOLDER_ID=0
QUARK_SHARE_EXPIRE_DAYS=7
```

Then open an internal resource link or call:

```bash
curl -X POST 'http://127.0.0.1:8888/api/resources/{resource_id}/open?wait=true'
```

The backend saves the source share into the owner account, creates a new owner share, stores it in `resources.owner_share_url`, and reuses it on later clicks.

## Notes

The real Quark transfer flow depends on unofficial web APIs and cookie-based auth. Keep the real client behind `QuarkService`, test it with mocked HTTP responses, and expect API/rate-limit changes.
