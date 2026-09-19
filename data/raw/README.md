# `data/raw` — source files (not vendored)

Raw source files are **not committed**. They are public, but large (~1.4 GB) and
the licence is "redistribute by reference". Re-create this directory with:

```bash
make data          # or: bash scripts/download_data.sh
```

## Expected layout once downloaded

```
data/raw/
└── power_laws_forecasting/
    ├── train.csv              341 MB   obs_id, SiteId, Timestamp, ForecastId, Value
    ├── metadata.csv            19 KB   SiteId, Surface, Sampling, BaseTemperature, *IsDayOff
    ├── weather.csv           1012 MB   Timestamp, Temperature, Distance, SiteId
    ├── holidays.csv           294 KB   Date, Holiday, SiteId
    └── submission_format.csv   51 MB   (competition artefact, unused by EcoTwin)
```

If this directory is empty, **nothing breaks**: `scripts/prepare_data.py` writes a
`NO_RAW_DATA` selection, the adapter registry falls back to the fixture adapters,
and the UI status bar switches to `SAMPLE FIXTURE`. See `docs/data_provenance.md`.
