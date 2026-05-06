# ============================================================
# EXTENSION INTEGRATION GUIDE
# How to wire the extension layer into the existing project
# IMPORTANT: Zero modification to any existing file required
# ============================================================

## What's in this extension layer

```
extensions/
├── backend/
│   ├── migrations/
│   │   └── 002_extension_schema.sql   ← New DB tables only
│   ├── data_pipeline/
│   │   └── pipeline.py                ← Standardization + AVS scoring
│   ├── connectors/
│   │   └── source_connectors.py       ← Amazon / Flipkart adapters
│   ├── comparison/
│   │   └── comparison_engine.py       ← Cross-source comparison
│   ├── api/
│   │   └── ext_routes.py              ← New /api/ext/* endpoints
│   ├── app_extension.py               ← Blueprint registration helper
│   └── run_with_extensions.py         ← Drop-in server entrypoint
└── frontend/
    └── src/
        ├── hooks/
        │   └── useExtApi.js            ← New API hook (doesn't replace useApi.js)
        ├── components/
        │   ├── search/
        │   │   ├── GlobalSearch.jsx
        │   │   └── GlobalSearch.css
        │   ├── comparison/
        │   │   ├── ComparisonView.jsx
        │   │   └── ComparisonView.css
        │   └── wishlist/
        │       ├── WishlistPanel.jsx
        │       └── WishlistPanel.css
        └── pages/
            ├── ExtensionHub.jsx        ← New page (wraps all new features)
            └── ExtensionHub.css
```

---

## STEP 1 — Copy extension files into the project

Copy the files from this extension folder into the existing project structure:

```bash
# Backend
cp -r extensions/backend/migrations/002_extension_schema.sql \
       v2_project/ecommerce_platform/backend/migrations/

cp -r extensions/backend/data_pipeline \
       v2_project/ecommerce_platform/backend/

cp -r extensions/backend/connectors \
       v2_project/ecommerce_platform/backend/

cp -r extensions/backend/comparison \
       v2_project/ecommerce_platform/backend/

cp extensions/backend/api/ext_routes.py \
       v2_project/ecommerce_platform/backend/api/

cp extensions/backend/app_extension.py \
       v2_project/ecommerce_platform/backend/

cp extensions/backend/run_with_extensions.py \
       v2_project/ecommerce_platform/backend/

# Frontend
cp -r extensions/frontend/src/hooks/useExtApi.js \
       v2_project/ecommerce_platform/frontend/src/hooks/

cp -r extensions/frontend/src/components/search \
       v2_project/ecommerce_platform/frontend/src/components/

cp -r extensions/frontend/src/components/comparison \
       v2_project/ecommerce_platform/frontend/src/components/

cp -r extensions/frontend/src/components/wishlist \
       v2_project/ecommerce_platform/frontend/src/components/

cp extensions/frontend/src/pages/ExtensionHub.jsx \
       v2_project/ecommerce_platform/frontend/src/pages/

cp extensions/frontend/src/pages/ExtensionHub.css \
       v2_project/ecommerce_platform/frontend/src/pages/
```

---

## STEP 2 — Run the extension DB migration

Run this AFTER the existing 001_schema.sql has been applied.
It only creates new tables — never modifies existing ones.

```bash
psql -U your_user -d your_db -f backend/migrations/002_extension_schema.sql
```

---

## STEP 3 — Start backend with extensions

Instead of running `python run.py`, use the new entrypoint:

```bash
cd backend
python run_with_extensions.py
```

This:
1. Calls the existing `create_app()` (unchanged)
2. Registers the `ext_bp` blueprint on top
3. All existing routes remain at `/api/*`
4. New routes appear at `/api/ext/*`

---

## STEP 4 — Wire the new page into the frontend

**Make ONE addition to the existing `App.jsx`** (the only file you touch):

```jsx
// At the top of App.jsx, add this import:
import ExtensionHub from "./pages/ExtensionHub";
import "./pages/ExtensionHub.css";

// Inside the App() function, add one line to the nav state:
// Change: const [page, setPage] = useState("dashboard");
// (no change needed to the state itself)

// Inside the JSX return, ADD this line (do not change any existing lines):
{page === "intelligence"  && <ExtensionHub />}
```

**And add the nav link in `Nav.jsx`** (one addition):

```jsx
// Add to the existing nav links array/list:
{ id: "intelligence", label: "🌐 Intelligence" }
```

That's the **only** change to existing files. Everything else is additive.

---

## STEP 5 — Optional: Add API keys for real data

Add to `backend/.env`:

```env
# Real Amazon data (from rapidapi.com → Real-Time Amazon Data)
RAPIDAPI_KEY=your_key_here

# Real Flipkart data (from scraperapi.com)
SCRAPERAPI_KEY=your_key_here
```

Without these, the connectors return realistic demo data automatically.

---

## New API Endpoints (all at /api/ext/)

| Method | Endpoint                              | Description                     |
|--------|---------------------------------------|---------------------------------|
| GET    | /api/ext/search                       | Global product search           |
| GET    | /api/ext/compare?q=...                | Cross-source comparison         |
| POST   | /api/ext/ingest                       | Fetch + ingest from a platform  |
| GET    | /api/ext/price-history/<std_id>       | Extension price history         |
| GET    | /api/ext/wishlist/<session_id>        | Get wishlist                    |
| POST   | /api/ext/wishlist/<session_id>        | Add to wishlist                 |
| DELETE | /api/ext/wishlist/<session_id>/<id>   | Remove from wishlist            |
| GET    | /api/ext/saved/<session_id>           | Get saved products              |
| POST   | /api/ext/saved/<session_id>           | Save a product                  |
| DELETE | /api/ext/saved/<session_id>/<id>      | Remove saved product            |
| GET    | /api/ext/stats                        | Extension data statistics       |

---

## Architecture diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     EXISTING SYSTEM (UNCHANGED)             │
│  products | market_prices | price_history | value_scores    │
│  /api/products | /api/scrape | /api/compute-scores  etc.    │
└──────────────────────┬──────────────────────────────────────┘
                       │ no cross-writes
                       │
┌──────────────────────▼──────────────────────────────────────┐
│                  EXTENSION LAYER (NEW)                      │
│                                                             │
│  standardized_products  ←  data_pipeline.process_batch()   │
│  ext_price_history      ←  tracked automatically           │
│  user_wishlist          ←  /api/ext/wishlist/*             │
│  saved_products         ←  /api/ext/saved/*                │
│  product_comparisons    ←  comparison_engine               │
│                                                             │
│  Connectors: Amazon US/UK/IN | Flipkart | Generic JSON     │
│  New APIs:   /api/ext/search | /api/ext/compare | etc.     │
│  New UI:     ExtensionHub → Search | Compare | Wishlist    │
└─────────────────────────────────────────────────────────────┘
```

## Data quality guarantees

- Deduplication: `UNIQUE(source, source_product_id)` constraint
- Schema: every record has `product_name, price, original_price, discount, rating, reviews, source`
- Currency: all prices normalized to USD on ingestion
- Scoring: `advanced_value_score` is a separate field — never overwrites `value_score`
- Isolation: no INSERT/UPDATE/DELETE on existing tables from extension code

---

## STEP 6 — Auth system setup

Run the auth migration after the extension schema:

```bash
psql -U your_user -d your_db -f backend/migrations/003_auth_schema.sql
```

New endpoints available:

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /api/ext/auth/register | Register (returns JWT) |
| POST | /api/ext/auth/login | Login (returns JWT) |
| GET  | /api/ext/auth/me | Get profile (Bearer required) |
| POST | /api/ext/auth/refresh | Refresh token |
| POST | /api/ext/auth/link-session | Link session saves to user |

Frontend: `ExtensionHubShell` renders a **Sign In / Register** button in the top bar. After login, all session wishlist/saved items are automatically linked to the user account.

---

## STEP 7 — Real Amazon & Flipkart data

Add to `backend/.env`:

```env
RAPIDAPI_KEY=your_key   # https://rapidapi.com → Real-Time Amazon Data
SCRAPERAPI_KEY=your_key # https://scraperapi.com (free tier available)
```

Without keys, `FakeStore` (free, no key needed) returns live demo data immediately. Both real connectors fall back to mock automatically on any error.

---

## STEP 8 — Price drop alerts

Price drops are checked every 4 hours by the background scheduler. The **🔔 badge** in the top bar of `ExtensionHubShell` polls `/api/ext/alerts/<session_id>` every 5 minutes and shows a dropdown of items that have hit their target price.

Set a target price when adding to wishlist:
```json
POST /api/ext/wishlist/<session_id>
{ "ext_product_id": "...", "target_price": 29.99 }
```

---

## STEP 9 — Comparison caching

Use the cached endpoint to avoid re-running expensive comparisons:

```
GET /api/ext/compare/cached?q=laptop&country=US
```

Results cached for 6 hours in `ext_comparison_groups` + `ext_comparison_members`. Check cached groups:

```
GET /api/ext/compare/groups
```

---

## STEP 10 — Pagination

All wishlist and saved endpoints support pagination:

```
GET /api/ext/wishlist/<session_id>/page?page=2&limit=20
GET /api/ext/saved/<session_id>/page?page=1&limit=50
```

Response includes: `total`, `page`, `limit`, `pages`. Original non-paginated endpoints (`/wishlist/<id>`, `/saved/<id>`) are unchanged.

---

## Complete API reference (all /api/ext/* endpoints)

| Method | Endpoint | Feature |
|--------|----------|---------|
| GET | /search | Global search + filters |
| POST | /ingest | Fetch & ingest from platform |
| POST | /compute-scores | Recompute advanced scores |
| GET | /compare | Live keyword comparison |
| GET | /compare/cached | Cached comparison (6h TTL) |
| GET | /compare/groups | List cached groups |
| GET | /compare/\<id\> | Product-specific match |
| GET | /price-history/\<id\> | Price time-series |
| GET/POST/DELETE | /saved/\<sid\> | Saved products |
| GET | /saved/\<sid\>/page | Paginated saved |
| GET/POST/DELETE | /wishlist/\<sid\> | Wishlist |
| GET | /wishlist/\<sid\>/page | Paginated wishlist |
| POST | /membership/\<sid\> | Batch save/wish check |
| GET | /alerts/\<sid\> | Price drop alerts (session) |
| GET | /alerts/all | All triggered alerts |
| GET | /stats | Extension stats |
| POST | /auth/register | Register user |
| POST | /auth/login | Login |
| GET  | /auth/me | Current user |
| POST | /auth/refresh | Refresh JWT |
| POST | /auth/link-session | Link session → user |
