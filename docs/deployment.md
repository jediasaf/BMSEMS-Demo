# Deploying EcoTwin AI

## The shape of it

EcoTwin is two processes, and only one of them belongs on Vercel.

| | What it is | Where it runs |
|---|---|---|
| `apps/web` | Next.js 15, React 19 | **Vercel** — this is what Vercel is for |
| `apps/api` | FastAPI + pandas, LightGBM, pandapower, CVXPY | **A container host** — Fly.io, Render, Railway, Cloud Run |

The backend does not fit Vercel's serverless model and it is not close. Its
dependency set is around 400 MB of wheels before any code, it reads ~94 MB of
Parquet and joblib from disk, and it warms per-facility caches at start-up —
including a transformer-capacity calibration that bisects on a load flow. That
is a long-lived process with a filesystem, not a function.

**A Vercel deployment on its own is not a working demo.** The interface will
load and every panel will say the API is unreachable, because it is. The
system bar states exactly that, with the URL it tried, rather than showing
eight identical red panels. Deploy the backend first.

---

## 1. Backend

The image is already built by the repository's `Dockerfile` and includes the
processed dataset, the trained models and the demo cache.

### Fly.io

```bash
fly launch --no-deploy --name ecotwin-api      # accept the detected Dockerfile
fly scale memory 2048                          # LightGBM + pandapower want room
fly deploy
fly open /health                               # expect status: ok
```

### Render / Railway / Cloud Run

Point the service at the repository root `Dockerfile`. It listens on `$PORT`
and needs no volume: the data ships in the image.

```bash
gcloud run deploy ecotwin-api \
  --source . --region europe-west1 \
  --memory 2Gi --cpu 2 --timeout 120 --allow-unauthenticated
```

### Check it before moving on

```bash
curl -s https://<your-api>/health | jq .components
# {"api":"ok","data":"ok","models":"ok","pandapower":"ok","boptest":"local"}

curl -s https://<your-api>/interview/verify | jq .ready     # must be true
```

`boptest: "local"` is expected and correct: the hosted deployment has no
BOPTEST instance, so the zone simulator is the in-process RC engine and every
result is labelled with it. `local Docker mode` (`make up-boptest`) runs
BOPTEST where it is reachable.

---

## 2. Frontend on Vercel

```bash
npm i -g vercel
cd apps/web
vercel link                                    # once, to create the project
vercel env add NEXT_PUBLIC_API_BASE production # paste the backend URL
vercel --prod
```

Or through the dashboard: import the repository, set **Root Directory** to
`apps/web`, and add the environment variable.

| Setting | Value |
|---|---|
| Root directory | `apps/web` |
| Framework | Next.js (detected) |
| Build command | `next build` (in `vercel.json`) |
| `NEXT_PUBLIC_API_BASE` | `https://<your-api>` — no trailing slash |

`NEXT_PUBLIC_API_BASE` is inlined at build time, so **changing it requires a
redeploy**, not just an environment edit.

### CORS

The backend allows every origin by default (`ECOTWIN_CORS_ORIGINS` unset), so
a fresh Vercel deployment works immediately. To lock it down:

```bash
fly secrets set ECOTWIN_CORS_ORIGINS=https://ecotwin.vercel.app
```

### Avoiding CORS entirely (optional)

Add a rewrite to `apps/web/vercel.json` and set
`NEXT_PUBLIC_API_BASE=/api`, so the browser only ever talks to your Vercel
domain:

```json
"rewrites": [
  { "source": "/api/:path*", "destination": "https://<your-api>/:path*" }
]
```

This is not committed, because a rewrite pointing at a host that does not
exist yet is a broken deployment rather than a default.

---

## 3. Verify the deployment

```bash
curl -s https://<your-api>/interview/verify | jq '.ready, .failed'
E2E_BASE_URL=https://<your-app>.vercel.app \
E2E_API_BASE=https://<your-api> \
  npx playwright test --config apps/web/playwright.config.ts
```

The end-to-end test drives all twelve curated steps, runs the optimiser and
asserts the transformer comes back under 100%. If it passes against the
deployed URLs, the demo works from a cold browser on the public internet —
which is the only definition of "deployed" worth having.

---

## Expected behaviour of a healthy public deployment

| | |
|---|---|
| Zone simulation | EcoTwin RC engine, labelled as such. Not BOPTEST. |
| First load | Preload runs once; the system bar reports how long it took |
| Control Lab | Live solve, ~0.5 s warm |
| EMS optimisation | Live solve, ~0.1 s warm |
| If a heavy solve fails | A recorded result for the *same scenario*, banner-marked SIMULATION REPLAY |
| If the dataset is absent | Everything reads SAMPLE FIXTURE; no value can be mistaken for real |

---

## What is deliberately not here

No Kubernetes, no message bus, no managed database. At six facilities and one
container they would be architecture theatre. `docs/interview_questions.md`
covers what would actually change at a thousand sites — and the answer starts
with the storage layer, not the orchestrator.
