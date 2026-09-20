# Deploying EcoTwin AI

## Current production state

|                    |                                                                       |
| ------------------ | --------------------------------------------------------------------- |
| Frontend           | https://ecotwin-ai-zeta.vercel.app — deployed and publicly reachable |
| Backend            | https://bmsems-demo.fly.dev — Fly.io `bmsems-demo`, ams, 1 GB, one always-on machine |
| Frontend → backend | `NEXT_PUBLIC_API_BASE=https://bmsems-demo.fly.dev` |

The frontend is correct and complete; it is waiting on a backend URL. Nothing
below is aspirational — the image builds, runs and passes `/interview/verify`
locally, and the manifests are sized from measurements of that run.

### Redeploying

The backend image is built from the committed `Dockerfile` and deployed to the
Fly app `bmsems-demo`. Two routes, both committed:

```bash
FLY_API_TOKEN=... bash scripts/deploy_backend.sh   # from a shell
```

or put the token in the repository and click:

1. `flyctl tokens create deploy --name ecotwin`
2. GitHub → **Settings → Secrets and variables → Actions → New repository
   secret**, named `FLY_API_TOKEN`
3. **Actions → Deploy backend → Run workflow**

`.github/workflows/deploy-backend.yml` then creates the app, deploys the
committed `fly.toml` (1 GB, one always-on machine, `/healthz` as the platform
check), waits for liveness, and asserts `/health` components and
`/interview/verify` `ready: true` before it reports success. It accepts the
token under `FLY_API_TOKEN`, `FLY_ACCESS_TOKEN`, `FLY_TOKEN` or
`FLYIO_API_TOKEN`, never prints it, and runs only on `workflow_dispatch` — a
deployment is a decision, not a side effect of committing.

To deploy from a shell instead:

```bash
FLY_API_TOKEN=... bash scripts/deploy_backend.sh
# or
RENDER_API_KEY=... bash scripts/deploy_backend.sh --render
```

Both refuse to run without a credential and neither reports a deployment it
did not make.

### Two things worth knowing about this deployment

**The account is on a Fly trial, so the machine stops after five minutes.**
`auto_stop_machines = false` and `min_machines_running = 1` cannot override
that; only a card on the account can. `auto_start_machines = true` means a
request still wakes it, at the cost of the measured ~24 s cold start. Add a
card before showing the demo.

**A build host that cannot reach a depot builder can still deploy.** Build the
image locally and hand Fly the result:

```bash
flyctl auth docker
docker build -t registry.fly.io/bmsems-demo:deployment-$(date +%s) .
docker push registry.fly.io/bmsems-demo:deployment-...
flyctl deploy --config fly.toml --app bmsems-demo --image registry.fly.io/... --ha=false
```

A deploy token can push to its own app's registry and deploy an existing app;
it cannot create apps or manage a remote builder, which is the correct scope.
If the app has never had public addresses, `flyctl ips allocate-v4 --shared`
and `allocate-v6` are needed once — without them health checks pass internally
while the public hostname refuses every connection.

### Why not Vercel, measured

The backend's runtime dependencies install to **483 MB** — pyarrow 135,
scipy 113, pandas 75, scikit-learn 57, numpy 40, pandapower 35, the rest
smaller — before any code, and it reads a further 94 MB of Parquet and joblib
from disk. Vercel's serverless function limit is 250 MB unzipped. This is not
a near miss that could be trimmed; it is a long-lived process with a
filesystem, which is what a container host is for.

## Two ways to host this

**Static recording (what the public demo runs).** The demo is deterministic:
seeded scenarios, a fixed replay window, optimisers that return the same
answer for the same inputs. So it can be recorded once and served as files.

```bash
make snapshot   # record every response the product can make, then check it
make static     # record, then build the frontend that serves the recording
```

`scripts/build_static_snapshot.py` drives the real API in-process and writes
`apps/web/public/snapshot/*.json`. The frontend reads those instead of a
backend when built with `NEXT_PUBLIC_SNAPSHOT=1`, which `vercel.json` sets.

What this buys: one platform, no container, no cold start, nothing to pay for,
nothing to wake up. What it costs: the hosted demo is a **replay**, and the
product says so — a `Recorded` chip in the status bar with the date, a line on
the About page, and a `_snapshot` marker on every payload.
`scripts/verify_snapshot.py` re-checks that the recording still holds up, so a
stale recording fails a command rather than an audience.

Nothing is fabricated by recording. Every figure was produced by the engines
named in its provenance — LightGBM, the RC zone model, pandapower, CVXPY — on
a real run. Only the delivery changed.

**Live backend (what `make demo` runs, and what a container host would run).**
Everything solves on request: the optimiser in ~140 ms, two pandapower load
flows to check its answer. This is the mode to run in front of anyone who asks
"is it actually computing?".

The rest of this document covers that second mode.

## The shape of it

EcoTwin is two processes, and only one of them belongs on Vercel.

|            | What it is                                    | Where it runs                                             |
| ---------- | --------------------------------------------- | --------------------------------------------------------- |
| `apps/web` | Next.js 15, React 19                          | **Vercel** — this is what Vercel is for                   |
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

### Measured requirements

Sized from running the production image, not from habit:

|                                        |                                                                                                |
| -------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Image                                  | 255 MB                                                                                         |
| Artifacts in image                     | 95 MB (90 MB Parquet, 4 MB models, 1 MB demo cache)                                            |
| Cold start to first `200 /healthz`     | **24 s** (16 s of it warm-up)                                                                  |
| RAM after warm-up                      | 502 MB                                                                                         |
| RAM after `/interview/verify`          | 522 MB                                                                                         |
| RAM peak under the whole demo workload | **548 MB**                                                                                     |
| Warm latency                           | `/healthz` 4 ms · `/health` 64 ms · overview 640 ms · Control Lab 805 ms · EMS optimise 133 ms |

So **1 GB** is the right size: 45% headroom over the measured peak. 512 MB
would OOM during warm-up. 2 GB is paying for nothing.

### Fly.io

`fly.toml` is committed with these numbers already in it.

```bash
flyctl deploy --config fly.toml --app bmsems-demo --remote-only
fly deploy
curl -s https://bmsems-demo.fly.dev/healthz        # {"status":"ok"}
```

`auto_stop_machines = false` and `min_machines_running = 1` are deliberate: a
machine that sleeps pays the 24 s cold start on the next request, and that
request is the one an interviewer is watching.

### Render

`render.yaml` is committed. **Do not use the free tier** — it spins down when
idle and puts a 24 s cold start in front of the first click. Starter (512 MB)
is too small; Standard is the smallest plan that fits.

### Cloud Run

```bash
gcloud run deploy ecotwin-api \
  --source . --region europe-west1 \
  --memory 1Gi --cpu 1 --timeout 120 \
  --min-instances 1 --allow-unauthenticated
```

`--min-instances 1` for the same reason: scale-to-zero means a cold start in
the demo.

### Check it before moving on

```bash
curl -s https://<your-api>/healthz                          # liveness, touches nothing
curl -s https://<your-api>/health | jq .components
# {"api":"ok","data":"ok","models":"ok","pandapower":"ok","boptest":"local"}

curl -s https://<your-api>/interview/verify | jq .ready     # must be true
```

Three endpoints, three questions: `/healthz` is the process alive (what the
platform check should poll), `/health` is every component healthy, and
`/interview/verify` is the demo actually ready.

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

| Setting                | Value                                    |
| ---------------------- | ---------------------------------------- |
| Root directory         | `apps/web`                               |
| Framework              | Next.js (detected)                       |
| Build command          | `next build` (in `vercel.json`)          |
| `NEXT_PUBLIC_API_BASE` | `https://<your-api>` — no trailing slash |

`NEXT_PUBLIC_API_BASE` is inlined at build time, so **changing it requires a
redeploy**, not just an environment edit.

### CORS

The origin list is closed, not `*`. The default already contains the two
production frontend aliases and local development:

```
http://localhost:3000, http://127.0.0.1:3000,
https://ecotwin-ai-zeta.vercel.app,
https://ecotwin-ai-jediasafs-projects.vercel.app
```

`allow_credentials` is False and the API has no cookies or auth headers, so
`*` is never paired with credentials — and an empty list now means _no_
cross-origin access rather than silently meaning _all_ of it. Override for a
different frontend:

```bash
fly secrets set ECOTWIN_CORS_ORIGINS=https://your-frontend.example.com
```

Preview deployments get their own origins and are deliberately **not** in the
list; add one explicitly if you need to test against a preview.

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

|                          |                                                                            |
| ------------------------ | -------------------------------------------------------------------------- |
| Zone simulation          | EcoTwin RC engine, labelled as such. Not BOPTEST.                          |
| First load               | Preload runs once; the system bar reports how long it took                 |
| Control Lab              | Live solve, ~0.5 s warm                                                    |
| EMS optimisation         | Live solve, ~0.1 s warm                                                    |
| If a heavy solve fails   | A recorded result for the _same scenario_, banner-marked SIMULATION REPLAY |
| If the dataset is absent | Everything reads SAMPLE FIXTURE; no value can be mistaken for real         |

---

## What is deliberately not here

No Kubernetes, no message bus, no managed database. At six facilities and one
container they would be architecture theatre. `docs/interview_questions.md`
covers what would actually change at a thousand sites — and the answer starts
with the storage layer, not the orchestrator.

### What the hosted build is told

`apps/web/vercel.json` sets both build-time variables explicitly:

```json
"env": { "NEXT_PUBLIC_SNAPSHOT": "1", "NEXT_PUBLIC_API_BASE": "" }
```

The second is not redundant. `NEXT_PUBLIC_*` variables are inlined at build
time wherever the source reads them, so a leftover `NEXT_PUBLIC_API_BASE` in
the Vercel project settings would be baked into the bundle — a dead backend
URL shipped to every visitor, and a claim in the artefact that contradicts
what the product does. Blanking it in `vercel.json` overrides the project
setting, so the repository decides, not a dashboard field nobody will
remember. `.github/workflows/verify-production.yml` fails the deployment if a
backend host appears in the served bundle.

If you connect this repository to Vercel through the GitHub integration rather
than the CLI, set **Root Directory** to `apps/web`. Everything else —
framework, build command, install command, headers, region — is in
`vercel.json`, so there is nothing to configure in the dashboard and no
environment variable to add.
