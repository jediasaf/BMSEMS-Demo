# Release readiness

What was verified, how, and what is still open. Every number here was produced
by running the thing it describes; nothing is carried over from an earlier
report.

_Replace the placeholders under **Build under test** on each release; the rest
is re-derived by `make check`, `make audit`, `make demo` and `make e2e`._

## Build under test

| | |
|---|---|
| Branch | `claude/zen-ptolemy-5hf381` |
| Commit | `e9abfc1` |
| Frontend | https://ecotwin-ai-zeta.vercel.app — deployed, publicly reachable |
| Backend | https://bmsems-demo.fly.dev — Fly.io app `bmsems-demo`, region ams, 1 GB, one always-on machine |
| Dataset | Power Laws: Forecasting Energy Consumption, 1.03 M records |
| Replay window | 2017-08-24 → 2017-08-27, 15-minute steps |

## Verification battery

| Check | Command | Result |
|---|---|---|
| Python tests | `pytest` | 204 passed |
| Lint | `ruff check .` | clean |
| Format | `black --check .` | clean |
| Types | `tsc --noEmit` | clean |
| Frontend lint | `next lint` | clean |
| Production build | `next build` | 9 routes, all static, no browser source maps |
| Browser suite | `playwright test` | 8 passed locally, and **8 passed against the public deployment** from a GitHub runner — the twelve demo steps, reset, the honest normal day, and `/interview/verify` |
| Provenance | `make audit` | every audited metric carries a badge from the closed vocabulary |
| Demo readiness | `GET /interview/verify` | `ready: true`, 10/10 checks |
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

Warm, median of three, measured from a GitHub runner against the public
deployment — the network an interviewer will be on, not the loopback:

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

A second run of the same battery, taken while the trial stopped the machine
part-way through, measured `/interview/verify` at **23.0 s** and the Control
Lab at **9.9 s** — the same code, paying cold starts. That gap is the entire
cost of the trial limitation in item 1 below, and it is why a card matters
more than any tuning.

The same endpoints, warm, against the local production build:

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

## Security posture

| | |
|---|---|
| Secrets in the tree or in git history | none (scanned for token, key and credential patterns) |
| `.env*`, `.vercel/`, credentials | gitignored; only `.env.example` is tracked, and it holds no secret |
| Secrets in `NEXT_PUBLIC_*` | none — the only such variable is the API base URL |
| Browser source maps in production | none emitted |
| CORS | closed allowlist, `allow_credentials=False`, tested: production origin and localhost pass, unknown and look-alike origins get no grant |
| Error responses | no stack traces, no filesystem paths; unhandled errors return an opaque id and are logged server-side |
| Request inputs | identifiers are length- and pattern-bounded and rejected with 422 before any handler |
| Authentication | none. Every endpoint is public and read-only, and there is no code path to a real controller |

## Open items

1. **The Fly account is on a trial, so the machine stops after five minutes
   of running.** The log says it plainly: `Trial machine stopping. To run for
   longer than 5m0s, add a credit card by visiting https://fly.io/trial`.
   `auto_stop_machines = false` and `min_machines_running = 1` are set and
   cannot override a trial limit.

   The demo still works, because `auto_start_machines = true`: the first
   request after an idle period wakes the machine and waits for it, which
   costs the measured ~24 s cold start (19 s of that is cache warm-up). For an
   interview that is a bad first click, so **add a card before the day**; no
   configuration change can substitute for it.

2. **BOPTEST is not live in the hosted deployment,** which `/health` reports
   as `boptest: local`. The zone simulator is the in-process RC engine, solved
   live on every request and labelled with its own engine everywhere it
   appears. It is never presented as BOPTEST.
3. **Rotate both deployment tokens.** A Fly.io deploy token and a Vercel token
   were each supplied to this work in plain text and must be treated as
   compromised: <https://fly.io/dashboard/personal/tokens> and
   <https://vercel.com/account/tokens>. Neither is committed anywhere in this
   repository.

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
