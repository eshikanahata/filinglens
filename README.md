# FilingLens

Explainable risk signals from SEC 10-K annual reports, built with AIOps practices.
Individual course project by Eshika Nahata (DA24B004).

A user picks a US company and sees how its latest annual report differs from the previous year's: a
risk signal, a plain-English list of what stands out, and detailed changes in the risk-factors section.
It is **decision support, not financial advice**, and the application says so. The engineering focus is the
lifecycle around the model: an automated and versioned pipeline, experiment tracking, a model registry,
containerised serving, monitoring and alerting, drift detection, and retraining with automatic rollback.

## Headline results

| Area | Result |
|---|---|
| Data | 54 companies, 318 10-K filings, 14 text features |
| Parsing | 318 of 318 filings parsed after excluding five companies: four with non-standard layouts and one with no 10-K returned by EDGAR (first run on all companies: 89.5%) |
| Parallelism (Ray) | 77 to 361 filings per minute from 1 to 8 workers (4.68x) |
| API latency | 95th percentile 18.9 ms over 162 requests, zero errors (single client, local machine) |
| Model quality | Champion (logistic regression) test ROC-AUC 0.44 (95% interval 0.30 to 0.60): **indistinguishable from chance**, reported openly |
| Drift | Real data: 1 of 14 features flagged, no retraining. Simulated shift: 14 of 14 flagged, retraining and rollback demonstrated |
| Tests | 126 automated tests passing; 27 manual system tests passing |
| Code quality and CI | flake8 0 warnings, black formatting; `lint` and `test` DVC stages gate the model export and every commit |

The model result is a statement about the data (202 training filings), not about the engineering. The
documents explain why, with confidence intervals and a positive-control test.

## Architecture

Seven containers under Docker Compose, loosely coupled over REST:

- **frontend** (Streamlit): the user interface; talks only to the backend.
- **backend** (FastAPI): validation, precomputed features, scoring, explanations, Prometheus metrics.
- **model-server** (MLflow serving): the exported champion model, returning probabilities. Verifies the model's
  SHA-256 checksum before serving.
- **prometheus** and **grafana**: metrics, eight alert rules, dashboard.
- **cadvisor**: CPU, memory and liveness of every container, scraped by Prometheus.
- **mlflow-ui**: experiment and model-registry browser.

The pipeline is a DVC graph of eleven stages: `lint` and `test` (continuous integration), then `download`, `parse`,
`prices`, `labels`, `features`, `train`, `drift`, `serving_data`, `export_model`. `export_model` depends on the test
summary, so no model is exported from code that fails its checks. See the figures in the High-Level Design document.

## Quick start

Prerequisites: Python 3.14 (the version the models are trained with and the containers use), Docker with the
Compose plugin, git, DVC (installed below), and pyenv if you want to run `mlflow run`.

```bash
python3.14 -m venv aiopsvenv && source aiopsvenv/bin/activate
pip install -r requirements.lock      # exact versions of every package

cp .env.example .env          # then set EDGAR_USER_AGENT (your name and a real contact address, SEC rule)
                              # and GRAFANA_ADMIN_PASSWORD
bash scripts/install_hooks.sh # lint and tests run before every commit

# Loughran-McDonald word list (free for academic use): download the Master Dictionary CSV from
# https://sraf.nd.edu, save it as data/external/LM_MasterDictionary.csv, then:
dvc add data/external/LM_MasterDictionary.csv

dvc repro                     # downloads filings and prices, trains, exports the model (needs internet)
docker compose up -d --build  # starts all seven services
```

If you have the DVC remote with the data, run `dvc pull` instead of the download steps in `dvc repro`.

| URL | What |
|---|---|
| http://localhost:8501 | The application |
| http://localhost:8000/docs | Backend API documentation |
| http://localhost:3000 | Grafana (user `admin`, password from `.env`; anonymous read-only viewing), dashboard "FilingLens" |
| http://localhost:9090 | Prometheus (targets, alerts) |
| http://localhost:5000 | MLflow experiments and model registry |
| http://localhost:8080 | cAdvisor (container metrics) |

Stop everything with `docker compose down`.

**After changing application code**, rebuild: `docker compose up -d --build backend frontend`. Recreating a
container restarts the same image and does not pick up code changes.

## Everyday operations

```bash
pytest -q                                          # automated tests (126)
dvc repro lint test                                # CI: flake8 and the test suite as DVC stages
mlflow run . -e test                               # the same tests in a freshly built environment (MLproject)
python scripts/measure_latency.py                  # API latency against the 1-second target
dvc repro drift                                    # check the latest filings for drift
python -m src.drift.retrain --simulate-shift       # demo: deliberate shift, drift detected, retraining
python -m src.drift.retrain --force --tolerance -1 # demo: a "worse" model is rolled back
dvc repro drift                                    # reset to the real drift result
docker compose up -d --force-recreate model-server backend   # load a newly exported model
```

Rollback by hand: move the `champion` alias of `filinglens-risk` in the MLflow registry to an earlier
version, then `dvc repro -f -s export_model` and recreate the model-server and backend containers.

## Repository layout

```
api/            FastAPI backend (no machine-learning libraries)
frontend/       Streamlit interface
src/            pipeline code: ingestion, parsing, labels, features, training, drift, serving
tests/          automated tests
scripts/        latency measurement, test summary, serving contract check, diagnostics
monitoring/     Prometheus config and alert rules, Grafana provisioning and dashboard
docker/         Dockerfiles for backend, frontend and model server
config/         company list (with documented exclusions)
docs/           documentation, figures, system test checklist and evidence
params.yaml     all tunable parameters (tracked by DVC)
dvc.yaml        the pipeline definition, including the lint and test stages
MLproject       MLflow Project entry points (pipeline, train, retrain, test)
python_env.yaml environment for MLflow Projects; requirements.lock pins every package
.flake8, pyproject.toml   code style settings (flake8, black)
```

Data, models and generated reports live in `data/`, `models/` and `reports/` and are versioned with DVC
(or Git for small reports).

## Documentation

| Document | Content |
|---|---|
| High-Level Design | Architecture, design decisions with alternatives and rationale |
| Low-Level Design | API endpoints with input and output specifications, data formats, metrics, algorithms |
| Test Plan | Strategy, test inventory, system test cases, traceability |
| Test Report | Results, acceptance criteria, problems found and resolved |
| User Manual | How to use the application, for a non-technical user |
| System test checklist | Step-by-step manual system tests with results (`docs/system_test_checklist.md`) |

## Known limitations

- No detectable predictive signal on the available data (acceptance criterion on beating the baseline is not met).
- Four companies with annual-report-style filings are excluded because their risk section has no standard heading, and
  Exxon Mobil (XOM) because the download returned no 10-K for it in the date window.
- Retraining re-fits on the same data window; with no new filings it reproduces the same model.
- Alerts are shown in Prometheus but not delivered anywhere.
- Traffic between services and to the browser is plain HTTP on localhost; nothing is encrypted in transit.
- Continuous integration runs locally (DVC stages and a git hook), as cloud services are not allowed.
- The free price source is unofficial and could change.

## Data sources and credits

SEC EDGAR (filings); Yahoo Finance via `yfinance` (prices, unofficial); Loughran, T. and McDonald, B. (2011),
"When Is a Liability Not a Liability? Textual Analysis, Dictionaries, and 10-Ks", *Journal of Finance* 66(1),
35-65 (sentiment word lists).

## Disclaimer

FilingLens is a course project. Nothing it shows is financial advice.
