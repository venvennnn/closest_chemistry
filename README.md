# Closest Chemistry

Discover what clicks in your closet.

Closest Chemistry answers a single question: **which purchases unlock the most distinct, rule-qualified outfit options with clothes you already own?** It is not a claim about attractiveness, physical fit, guaranteed wear, or reduced returns. Exact search is exact under the declared compatibility rules, not objective fashion truth.

This repository is a production-shaped application: Next.js App Router, FastAPI, a PostgreSQL-backed worker, local or optional object storage, Gemini extraction, and YouCam virtual try-on. There is **no sign-in**. One shared anonymous session owns the closet. Empty databases show onboarding. Missing credentials produce actionable configuration errors. No wardrobe, catalogue, price, metric, or preview is fabricated.

## Architecture

| Piece | Stack | Deploy |
| --- | --- | --- |
| Web | Next.js 15 App Router, TypeScript, Tailwind, TanStack Query, Recharts, Cytoscape.js | Vercel |
| API | Python 3.12, FastAPI, Pydantic, SQLAlchemy, Alembic, Pillow, HTTPX, Google GenAI SDK | Render (Docker) |
| Worker | Same Python package, persistent process | Render worker |
| Data | PostgreSQL (Render or Compose). Photos on API disk, or optional private bucket | Render Postgres |

Expensive work (Gemini extraction, analysis, YouCam) returns **HTTP 202** plus a durable job id. The worker claims jobs with `FOR UPDATE SKIP LOCKED`, renewable leases, heartbeats, bounded attempts, and crash recovery. In-process background tasks are not used.

## Product language

- **Rule-qualified outfit options** — complete templates that pass published colour, pattern, formality, exclusion, and category rules.
- Compatibility edges are explainable rule matches, not user approval.
- Network node placement is a **category layout**, not an embedding.
- Algorithm superiority under `f(A)` is not proof of usefulness.
- Percentage optimality gaps are **undefined when the exact optimum is zero**.
- YouCam results are labelled **live** or **cached**. Cached results are never silently substituted for a requested live preview.

## Local development

```bash
cp .env.example .env
# fill Supabase, Gemini, and YouCam values you actually have

docker compose up --build
```

Or run pieces separately:

```bash
# API
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://chemistry:chemistry@localhost:5432/closest_chemistry
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# Worker (optional if the API runs start-api.sh, which starts a worker too)
python -m app.worker

# Web
cd frontend
npm ci
npm run dev
```

Health: `GET /healthz`. Readiness (database plus credential flags): `GET /readyz`.

### Tests

Synthetic garments are used **only** in isolated unit tests.

```bash
cd backend
pytest
```

Frontend typecheck/build:

```bash
cd frontend
npx tsc --noEmit
npm run build
```

## Credential provisioning

| Variable | Purpose | If missing |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy Postgres URI (`postgresql+psycopg://`) | API/worker refuse to start |
| `AUTH_MODE` | `single` (default): one shared closet. `session` only for tests/multi-tab isolation | Defaults to one user |
| `SUPABASE_SERVICE_ROLE_KEY` | Optional private bucket writes | Local filesystem fallback |
| `GEMINI_API_KEY` + `GEMINI_MODEL` | Outfit photograph extraction | Extraction returns 503. Model must be a documented identifier (`gemini-3.8-flash` recommended) |
| `YOU_CAM_API_KEY`, `YOU_CAM_BASE_URL`, `YOU_CAM_UNIT_COST`, `YOU_CAM_ENABLED_CATEGORIES` | Live try-on | Try-on returns 503. Empty enabled categories block paid jobs |

Sign-in is not used. In `AUTH_MODE=single` every request is the same owner (`local`). Photos default to `LOCAL_STORAGE_DIR` on the API machine.

YouCam documented flow (Perfect Corp AI Clothes v4):

1. `POST /s2s/v2.0/file`
2. Upload bytes to the returned presigned URL
3. `POST /s2s/v2.0/task/cloth-v4` with `src_file_id` / `ref_file_id`
4. `GET /s2s/v2.0/task/cloth-v4/{task_id}` every 10s, honouring `Retry-After`

Official unit table currently lists 2 units for AI Clothes VTO. HTTP calls are not treated as billable units. Daily reserves are estimates until a provider invoice is reconciled.

Gemini uses the Google GenAI SDK `models.generate_content` path with structured JSON (`ExtractionPayload`). Prompt, model, and source-image hashes are stored. Model self-reported confidence is not a calibrated probability.

## User journey

1. Open the app. Grant consent for external image processing. No account is created.
2. Upload up to 15 outfit photographs and a separate try-on photo. Signatures, dimensions, byte limits, and decoding are checked; EXIF is stripped; orientation is normalised.
3. Extraction runs asynchronously. Bounding-box crops become editable garment cards. Nothing is counted until confirmation.
4. Merge repeat appearances only after explicit confirmation. Colour similarity never auto-merges.
5. Add 4–10 real candidates via **upload-and-enter-price** (supported production path). Public HTTPS URLs are fetched only after SSRF checks; JSON-LD Product/Offer is read when present. Missing prices are never inferred by an LLM.
6. Choose budget and occasion. Exact search enumerates `2^n` (n ≤ 10) under pins, exclusions, and optional item limits. Ties break by lower cost, then fewer items, then stable ids.
7. Inspect the five graphs (all from persisted analysis JSON) and request a **fresh** YouCam task for supported combinations.

Objective: \(f(A)=|O(W \cup A)|-|O(W)|\) where \(O(S)\) is the set of qualified **cluster** ids achievable from set \(S\). Clusters are computed once on the full wardrobe-plus-cart snapshot.

## Five graphs

Editorial cream canvas, pink connections, no grid lines.

1. **Combination hub** — selected piece in the centre, owned/considering neighbours, explainable edges after a persisted analysis (layout, not an embedding).
2. **Outfit unlock ranking** — standalone `f({x})` versus basket-conditional contribution.
3. **Budget frontier** — exact best `f(A)` at discrete price breakpoints (step chart, never smoothed).
4. **Synergy matrix** — `f({i,j})-f({i})-f({j})` with complementarity versus overlap.
5. **Algorithm comparison** — exact, dynamic marginal-yield-per-cost greedy, cheapest-first, standalone-yield ranking. Greedy has **no** approximation guarantee; complementarity means `f` need not be submodular.

## Deployment

1. **Postgres**: Render Postgres, Railway Postgres, or Compose. Point `DATABASE_URL` at it (`postgresql+psycopg://...`).
2. **API / worker**: Docker from `backend/`. `start-api.sh` runs `alembic upgrade head`, starts a worker in the same container, then uvicorn. Set `GEMINI_API_KEY` on that service. Confirm `/healthz` and `/readyz`.
3. **Railway**: create a service from this GitHub repo with **Root Directory = `backend`** (not the repo root, not `frontend/`). Builder: Dockerfile. Redeploy after pulling this start script so extract jobs are claimed. A second worker from `backend/Dockerfile.worker` is optional.
4. **Frontend on Vercel**: root `frontend/`. Set **server** env `API_URL` to the API origin (no trailing slash). The browser calls same-origin `/v1`; Next.js proxies. Also set `CORS_ORIGINS` on the API to the Vercel origin. Provider keys stay server-side.

## Recovery

- Expired leases return to `queued` on the next worker loop.
- Ambiguous YouCam submissions set `unit_status=needs_reconcile` and do not blindly resubmit.
- Successful YouCam bytes are copied to private storage before provider URLs expire.
- `DELETE /v1/workspace` removes owned rows and stored objects. **Supabase backups and YouCam/Gemini provider retention are outside this control plane.**
- Retention deadlines are stored on consents (`RETENTION_DAYS`).

## Security

- No accounts. Default mode is one shared anonymous owner (`local`). Tests may send `X-Session-Id` to isolate tenants.
- Idempotency keys on extract / analyse / try-on.
- Per-user daily unit reserves and concurrency limits.
- Logs carry job ids and timings only — never photos, tokens, or signed URLs.
- Product URL fetch: HTTPS only, DNS re-check, block private/reserved IPs, revalidate redirects.

## Live verification status

Consented live Gemini extraction and YouCam smoke tests were **not executed in this environment**. Required secrets (`GEMINI_API_KEY`, `YOU_CAM_API_KEY`, a reachable Postgres URL, and rights-cleared photographs) are not present here.

Until those run, do **not** label the build production-verified. After you provision credentials:

1. Upload a consented outfit photo; record the redacted job id, model id, and latency from `/v1/jobs/{id}`.
2. Enable one YouCam category only after a consented live success. Official docs conflict on lower-body product-only references — keep `lower_body` disabled until a real worn-outfit reference succeeds.
3. Click **Generate live try-on** and confirm the response is labelled live, with a redacted `task_id` and estimated units (documented cost: 2 / task unless your contract says otherwise).
4. Restart API and worker and confirm the analysis JSON and copied try-on asset persist.

## Compatibility rules (compat-v1)

MVP categories: top, bottom, dress, optional outerwear, optional footwear. Footwear is included only when the analysis flag is on. Templates: top+bottom or dress, optionally plus outerwear.

- Unknown colour, pattern, or formality → review, not invented compatibility.
- Neutrals pair with any known family; complementary saturated mains are rejected.
- Two different busy pattern families on main garments are rejected.
- User-rejected looks are excluded on the next versioned recomputation. That is not model training.

## Guided flow

A guided tour is allowed only when an administrator supplies rights-cleared photographs, garment references, sourced products, and documented consent. This repository ships **no** such assets. The product therefore requires user uploads. “Generate live try-on” always enqueues a YouCam job marked live; cache hits stay distinctly labelled and are not used as a silent fallback when `force_live=true`.
