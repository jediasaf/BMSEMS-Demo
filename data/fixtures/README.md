# `data/fixtures`

The fixtures are **code, not files**: `core/adapters/building/fixture.py` and
`core/adapters/power/fixture.py` generate them deterministically from a fixed
seed. That keeps them in version control as readable, reviewable generators
rather than as opaque blobs, and it makes the generating physics — a base load,
a Gaussian occupancy profile and a degree-day HVAC response about a 17 °C
balance point — part of the thing being reviewed.

Everything they emit is tagged `SAMPLE FIXTURE` in provenance, and the demo
status bar switches to `SAMPLE FIXTURE` mode whenever they are in use.

This directory exists for **drop-in overrides**: place a parquet or CSV here and
point a fixture adapter at it when you need a specific shape for a test or a
reproduction. Nothing here is loaded automatically.
