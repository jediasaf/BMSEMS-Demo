# Release readiness

What was verified, how, and what is still open. Every number here was produced
by running the thing it describes; nothing is carried over from an earlier
report.

_Replace the placeholders under **Build under test** on each release; the rest
is re-derived by `make check`, `make audit`, `make snapshot`, `make demo` and
`make e2e`._

## Build under test

| | |
|---|---|
| Branch | `claude/zen-ptolemy-5hf381` |
| Commit | `81d7088` |
| Hosted demo | https://ecotwin-ai-zeta.vercel.app — **not yet serving this build**, see item 1 under Open items |
| What ships | a **recording**: 1389 files, 10.3 MB, taken 2026-09-20T11:23Z |
| Live mode | `make demo` — FastAPI plus the whole science stack, every answer solved on request |
| Dataset | Power Laws: Forecasting Energy Consumption, 1.03 M records |
| Replay window | 2017-08-24 → 2017-08-27, 15-minute steps |

## How the public demo is hosted

The product runs in two modes, and the difference matters enough to state up
front.

**Live** (`make demo`, and what a container host would run) computes
everything on request: LightGBM forecasts, the RC zone simulation, the CVXPY
solve, two pandapower load flows to check the optimiser's answer.

**Recorded** (what the hosted demo serves) is that same run, written to files.
`scripts/build_static_snapshot.py` drives the real API in-process across every
scenario and every replay position the slider can reach, and writes each
response to `apps/web/public/snapshot/`. The frontend reads those files when
built with `NEXT_PUBLIC_SNAPSHOT=1`.

Nothing is fabricated by recording. Every figure was produced by the engine
named in its provenance, on a real run. Only the delivery changed — and the
product says which mode it is in: a `Recorded` chip with the date in the status
bar, a line on the About page, and a `_snapshot` marker on every payload.

Why: the backend needs ~550 MB of RAM and a filesystem, which is a container,
which is a paid instance. The free tier it was on stopped the machine after
five minutes, and a demo that answers the first click with a timeout is not a
demo. Recording removes the server from the critical path entirely. The
container path still exists — `Dockerfile`, `fly.toml`, `docs/deployment.md` —
and is the mode to run in front of anyone who asks "is it actually
computing?".

## Verification battery

| Check | Command | Result |
|---|---|---|
| Python tests | `pytest` | 208 passed, eight consecutive runs |
| Lint | `ruff check .` | clean |
| Format | `black --check .` | clean |
| Types | `tsc --noEmit` | clean |
| Frontend lint | `next lint` | clean |
| Production build | `next build` | 9 routes, all static, no browser source maps |
| Browser suite | `playwright test` | 8 passed against the **recorded build**, built exactly as Vercel builds it (no `.env.local`, blank API base), with no backend running: the twelve demo steps, reset, the honest normal day, the API-base rules, and a sweep that fails on any missing file or console error. The ninth test asks a live backend for its verdict and skips when there is none. |
| Recording | `scripts/verify_snapshot.py` | consistent: recorded verdict `ready` with 10/10 checks, every payload marked as a recording, both gates still reached |
| Provenance | `make audit` | every audited metric carries a badge from the closed vocabulary |
| Demo readiness | `GET /interview/verify` | `ready: true`, 10/10 checks |
| Thread safety | `pytest tests/test_network.py` | the load-flow model is solved from several threads at once and every read matches the single-threaded answer |
| Known limitation | both gates still say no somewhere | the network gate rejects 18 of 54 over-nameplate replay positions; the recording keeps those rejections rather than only the flattering ones |
| Accessibility | axe-core, WCAG 2.0/2.1 A + AA, all seven routes | no violations |

## What the demo claims, and what checks it

`/interview/verify` re-derives every headline number on demand. It is the
single command to run before showing the product to anyone.

| Claim | Check |
|---|---|
| The injected day produces findings | `bms_scenario_raises_an_insight` |
| Those findings produce an action | `bms_scenario_proposes_an_action` |
| The simulator reports energy, peak and comfort | `bms_simulation_reports_energy_and_comfort` |
| The simulator **accepted** the proposal | `bms_simulation_accepted_by_the_gate` |
| A normal day stays quiet | `bms_baseline_stays_quiet` |
| The EV surge exceeds transformer capacity | `ems_scenario_exceeds_transformer_capacity` |
| The optimiser brings it back under | `ems_optimiser_returns_below_capacity` |
| EV energy is conserved | `ems_optimiser_conserves_ev_energy` |
| The **post-action load flow** accepts the dispatch | `ems_post_action_network_accepted` |
| A normal day has no violation | `ems_baseline_has_no_violation` |

Two of these are gates that can say no, which is the point of them: the zone
simulator may reject a setpoint proposal, and the second pandapower solve may
reject a dispatch. Both have unit tests that prove they reject — a gate that
has never failed in a test is decoration.

## Measured performance

### The hosted demo

Every response is a file. Median of three against the production build, served
locally; on Vercel the same files come off a CDN:

| | |
|---|---|
| Any page | 2 ms |
| `/bms/overview` base (the 56 kB timeline) | 2 ms |
| `POST /ems/optimise` (recorded) | 1 ms |
| `/bms/control-lab` (recorded) | 1 ms |
| Whole recording | 1389 files, 10.3 MB |
| Cold start | none — there is no server to start |

There is no slow first click, because there is nothing to wake. What this
buys is the reason to accept a replay at all; what it costs is stated on
screen.

### The live backend

Measured 2026-09-19 against the container deployment, from a GitHub runner —
the network an interviewer would have been on, not the loopback. That host is
no longer running (see **Open items**); the numbers stand as a record of what
the compute path costs over a real network:

| Endpoint | |
|---|---|
| `/healthz` | 219 ms |
| `/health` (every component, including a real load flow) | 260 ms |
| `/bms/overview` (injected scenario) | 361 ms |
| `/bms/control-lab` (two zone simulations + a convex solve) | 954 ms |
| `/ems/portfolio` (six facilities) | 274 ms |
| `/ems/network` (load flow) | 268 ms |
| `POST /ems/optimise` (LP + two load flows) | 336 ms |
| `/interview/verify` (re-runs every claim) | 2.0 s |

Most of each figure above is transatlantic round trip to ams.

A second run of the same battery, taken while the free tier stopped the
machine part-way through, measured `/interview/verify` at **23.0 s** and the
Control Lab at **9.9 s** — the same code, paying cold starts. That gap is why
the hosted demo is a recording.

The same endpoints, warm, against the local production build — this is what
`make demo` gives you, and what the recording was made from:

| Endpoint | |
|---|---|
| `/healthz` | 2 ms |
| `/health` | 64 ms |
| `/status` | 2 ms |
| `/bms/overview` (injected scenario) | 184 ms |
| `/bms/insights` | 2 ms |
| `/bms/assets` | 27 ms |
| `/bms/control-lab` (zone simulation ×2) | 838 ms |
| `/ems/portfolio` (six facilities) | 48 ms |
| `/ems/network` (load flow) | 68 ms |
| `/ems/risk` | 29 ms |
| `POST /ems/optimise` (LP + two load flows) | 139 ms |
| `/interview/verify` (re-runs every claim) | 2.0 s |

Backend container, measured from the production image:

| | |
|---|---|
| Image | 255 MB |
| Cold start to first `200 /healthz` | 24 s (16 s of it warm-up) |
| RAM after warm-up | 502 MB |
| RAM peak under the whole demo workload | **548 MB** |
| Therefore | **1 GB** instance; 512 MB would OOM during warm-up |

## A defect found and fixed during this release

Worth recording because of what it touched, and because it was found by the
test suite rather than by a demo going wrong.

**Symptom.** `test_ev_surge_creates_a_risk_the_optimiser_resolves` failed on
CI roughly one run in three and never locally, with nothing but `assert
False`. Instrumenting the assertion, then the capacity calibration underneath
it, showed the transformer capacity for one facility answering 144.940,
144.834 and **131.683 kW** on three calls in the same process from identical
inputs, and a 100 kVA site answering **50.042 kW** instead of 91.013.

**Cause.** Each facility has one pandapower model, shared by every caller, and
a load flow is not an atomic read: `solve` writes the loads in, runs
Newton-Raphson, then reads the results back. The cold-start fix (open item 3)
moved the cache warm-up onto a background thread, and that thread calibrates
every facility's capacity while request handlers are already solving. The
three steps interleaved, and callers got answers belonging to neither load.
The capacity bisection, being nothing but a sequence of solves, amplified it:
a probe that read another thread's loading walked the bracket the wrong way
and collapsed it.

**Why it mattered.** That capacity is the cap the EMS optimiser is held to and
the denominator of every transformer-loading percentage on screen. A wrong
one makes the flagship EMS claim wrong, in the direction of *understating* the
optimiser — or, worse, of showing a dispatch as accepted against a cap that is
not the transformer's.

**Fix.** The model is serialised with a reentrant lock, held for a whole
capacity search rather than per probe. Solves take single-digit milliseconds,
so the cost is not measurable. Two tests in `tests/test_network.py` reproduce
the race and fail without the lock. Separately, the bisection now checks that
its bracket contains the answer and logs and falls back to the nameplate
estimate when the search does not settle, instead of returning its last guess
as though it were a measurement.

**Blast radius.** The recording was taken from a process that ran the same
background warm-up, so it was regenerated after the fix and re-verified.

## Security posture

| | |
|---|---|
| Secrets in the tree or in git history | none (scanned for token, key and credential patterns) |
| `.env*`, `.vercel/`, credentials | gitignored; only `.env.example` is tracked, and it holds no secret |
| Secrets in `NEXT_PUBLIC_*` | none — the only such variable is `NEXT_PUBLIC_SNAPSHOT=1` |
| Browser source maps in production | none emitted |
| Cross-origin requests | none: the hosted build fetches only same-origin files. The API's own CORS is still a closed allowlist with `allow_credentials=False`, tested so that unknown and look-alike origins get no grant |
| Error responses | no stack traces, no filesystem paths; unhandled errors return an opaque id and are logged server-side |
| Request inputs | identifiers are length- and pattern-bounded and rejected with 422 before any handler |
| Authentication | none. The hosted build is static files. In live mode every endpoint is public and read-only, and there is no code path to a real controller |
| Attack surface of the hosted demo | static JSON and prerendered HTML. No server-side execution, no database, no inbound write path |

## Open items

1. **This build is not published yet.** The Vercel URL above still serves the
   previous build, which calls a backend that is no longer running — so the
   public demo is currently broken and this commit is the fix. Publishing it
   needs one thing that cannot be done from here: either a valid Vercel token,
   or the Vercel GitHub integration installed on the repository (Root
   Directory `apps/web`; nothing else to configure, since `vercel.json`
   carries the rest). The CLI token used on 2026-09-19 now returns
   `User not found`.

2. **The hosted demo is a replay, not a live computation.** This is a
   deliberate trade, not an oversight, and the product states it in three
   places rather than hiding it. `make demo` runs the same code live in about
   a minute, and `scripts/verify_snapshot.py` re-checks that the recording
   still agrees with what the demo claims, so a stale recording fails a
   command rather than an audience.

   The recording has to be regenerated when the API's shape or numbers change
   (`make snapshot`). A response shape the UI asks for and the recorder never
   captured is a missing file; `e2e/snapshot.spec.ts` fails on exactly that,
   which is how the one gap found so far was found.

3. **The container deployment that was verified on 2026-09-19 is no longer
   running.** It was on a free tier that stopped the machine after five
   minutes: `Trial machine stopping. To run for longer than 5m0s, add a
   credit card`. `auto_stop_machines = false` and `min_machines_running = 1`
   cannot override that.

   The wake path was worth fixing before abandoning it, and the fix stands in
   the code: a woken machine originally took **94 s** to bind — none of it
   our code, all of it CPU-throttled imports of the ~483 MB scientific stack
   read cold on a shared vCPU. Moving the cache warm-up behind the lifespan
   yield and deferring the service-layer imports into the handlers took
   `import apps.api.main` from 5.10 s to 0.58 s, and **cold start to serving
   `/healthz` from 94 s to 2 s**, measured twice. Anyone redeploying this to
   a paid instance gets that for free.

4. **BOPTEST is not live,** which `/health` reports as `boptest: local`. The
   zone simulator is the in-process RC engine, solved on every request in live
   mode and labelled with its own engine everywhere it appears. It is never
   presented as BOPTEST.
5. **Rotate both deployment tokens.** A Fly.io deploy token and a Vercel token
   were each supplied to this work in plain text and must be treated as
   compromised: <https://fly.io/dashboard/personal/tokens> and
   <https://vercel.com/account/tokens>. Neither is committed anywhere in this
   repository. The Vercel one has already stopped working, which is the right
   outcome; the Fly one has not been confirmed revoked.

## Known limitations

These are properties of the prototype, not defects to be fixed before a demo.
They are stated in `README.md` and on screen.

- A 3-day replay window, because the source publishes 10-day blocks and five
  days go to the forecaster's lags.
- A single-zone thermal model calibrated against whole-site demand, because the
  source has no zone telemetry. Credible physics, not a validated model of a
  specific building.
- Two sites' prediction intervals under-cover (68% and 73% against a target of
  80%). Reported in the model card rather than smoothed over.
- Weather is the recorded observation standing in for a vendor forecast.
- Anomaly labels are heuristics. The UI says "possible causes", never a
  diagnosis.
- The load flow is balanced and cannot see phase imbalance, which is a real
  limitation for single-phase EV charging on a three-phase feeder.
