# FilingLens

AIOps-driven system for explainable risk signals from SEC 10-K filings.
Individual course project (Eshika Nahata, DA24B004).

**Status: Phase 1 (Week 1)** — ingestion, Ray parsing, first DVC stages.

## Layout
```
config/tickers.txt        fixed company universe
params.yaml               DVC-tracked parameters
dvc.yaml                  pipeline: download -> parse   (features/train/evaluate come later)
src/ingestion/            EDGAR client (throttled, retrying) + download stage
src/parsing/              HTML -> text -> Item 1A extractor, Ray parse stage, Ray benchmark
tests/                    unit + small Ray integration test
docs/                     architecture diagram, HLD, LLD, test plan, user manual (to write)
reports/                  metrics written by stages (tracked in Git, not DVC cache)
```

## Setup
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env     # then put your real contact in EDGAR_USER_AGENT
export $(grep -v '^#' .env | xargs)                   # Windows: set it with setx / $env:
bash scripts/init_repo.sh                              # git init + dvc init + first commit
```

## Run
```bash
pytest                                  # all tests should pass offline
dvc repro                               # download -> parse
python -m src.parsing.benchmark_ray     # 1 vs 2 vs 4 workers -> reports/ray_benchmark.json
dvc metrics show                        # parse success rate, throughput
```

## Phase 1 definition of done
- [ ] `dvc repro` completes for the full ticker list
- [ ] Parse success rate >= 95% (`reports/parse_metrics.json`); failures listed in `reports/parse_failures.csv`
- [ ] `reports/ray_benchmark.json` shows speedup over 1 worker
- [ ] `dvc dag` output saved for the docs
- [ ] Architecture diagram drafted in `docs/`

## Known limitations (to revisit after first real run)
- Item 1A extraction is regex-based; expect some filings to fail. Check the failure CSV and refine `section_extractor.py`.
- Only the `recent` block of EDGAR submissions is read, which covers a 4-year window for these large caps.
- Fiscal-year labelling uses `report_date` (period end), not filing date.
