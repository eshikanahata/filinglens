# Phase 3 runbook: serving, API, UI, monitoring, Docker Compose

## What is new
| Piece | Where | Role |
|---|---|---|
| Backend API (FastAPI) | `api/` | validation, features, scoring via model server, `/metrics` |
| Frontend (Streamlit) | `frontend/` | company analysis, pipeline console, help page; REST calls to backend only |
| `serving_data` stage | `src/serving/build_serving_data.py` | precomputes per-filing features, percentiles, changed terms |
| `export_model` stage | `src/serving/export_model.py` | copies registry `champion` into portable `models/champion` |
| Containers | `docker/`, `docker-compose.yml` | model-server, backend, frontend, prometheus, grafana, mlflow-ui |
| Monitoring config | `monitoring/` | Prometheus scrape config, Grafana datasource + 11-panel dashboard |
| Change to training | `src/training/train.py` | model is now logged with `predict_proba` so the server returns probabilities |

## Apply (merge, do not replace)
```bash
cd ~/Documents/ml_project/filinglens
cp dvc.yaml dvc.yaml.bak && cp requirements-dev.txt requirements-dev.txt.bak
unzip -o ~/Downloads/filinglens_phase3.zip -d /tmp/p3
cp -r /tmp/p3/filinglens/. . && rm -rf /tmp/p3
pip install -r requirements-dev.txt
pytest -q                      # expect 77 passed here (+1 for your .env test = 78)
```

## Build the artefacts
```bash
dvc repro
```
Expect `train` to rerun (its code changed). It registers **version 2** of `filinglens-risk` and moves the
`champion` alias to it; metrics should be identical because seeds are fixed. Then `serving_data` and
`export_model` run and create `data/serving/` and `models/champion/`.

Optional contract check (starts a real MLflow server briefly, no Docker):
```bash
PYTHONPATH=. python scripts/check_serving_contract.py        # should end with ALL OK
```

## Run everything
```bash
docker compose version          # needs the compose plugin
docker compose up --build       # first build takes a few minutes
```
| URL | What |
|---|---|
| http://localhost:8501 | the application (frontend) |
| http://localhost:8000/docs | backend API documentation (interactive) |
| http://localhost:3000 | Grafana (login admin / admin; dashboard "FilingLens") |
| http://localhost:9090/targets | Prometheus (target `filinglens-backend` should be UP) |
| http://localhost:5000 | MLflow experiments and registry |

## Smoke test (about 5 minutes)
```bash
curl -s localhost:8000/health                                  # status ok, model_server up
curl -s localhost:8000/analysis/AAPL | python -m json.tool | head -40
curl -s localhost:8000/analysis/NOTATICKER                     # friendly 404 JSON
curl -s localhost:8000/metrics | grep ^filinglens_ | head
```
Then use the UI (pick a few companies), open the **Pipeline console** page, and check that the Grafana
panels show data (request rate appears after a few analyses).

## Rollback demo (for the viva)
```bash
python - << 'PY'
import mlflow
from mlflow.tracking import MlflowClient
mlflow.set_tracking_uri("sqlite:///mlflow.db")
MlflowClient().set_registered_model_alias("filinglens-risk", "champion", "1")   # back to version 1
PY
dvc repro -f export_model          # -f: the stage's dependencies did not change, so force it
docker compose restart model-server backend
curl -s localhost:8000/analysis/AAPL | python -m json.tool | grep -A3 '"model"'   # version "1"
```
Note: version 1 was logged before the `predict_proba` change, so it returns class labels and the backend
will answer 503 with a friendly message. That is itself a useful demonstration of the error handling; roll
forward again by pointing the alias back at version 2.

## Design choices worth knowing
- **Loose coupling:** frontend knows only `BACKEND_URL`; backend knows only `MODEL_SERVER_URL` and the
  `predict_proba` contract; neither imports training code. A test enforces this.
- **Portable model:** `export_model` copies the champion out of the registry, because registry artifact
  paths are absolute host paths that do not exist inside containers.
- **Pipeline metrics without a push gateway:** the backend reads the stage reports at scrape time and
  exposes them as Prometheus gauges, so Grafana always reflects the latest `dvc repro`.
- **"What stands out" is descriptive:** percentiles versus the rest of the dataset, not a causal explanation
  of the model score (the model is at chance level; the UI says so).

## Phase 3 definition of done
- [ ] `docker compose up --build` brings up all six services; backend and model-server show healthy
- [ ] Frontend analyses a company end to end; unknown ticker and backend-down cases show friendly messages
- [ ] Prometheus target UP; Grafana dashboard shows request, latency and pipeline panels
- [ ] Pipeline console page shows stage status, Ray benchmark, model comparison and embedded panels
- [ ] Rollback demonstrated once
- [ ] Architecture diagram and HLD updated to match what was actually built

## Not verified in my environment (check these first if something fails)
Image builds, `docker compose up`, Grafana provisioning and iframe embedding, and the Prometheus scrape.
What I did verify: all unit and integration tests, a real MLflow server returning probabilities through the
backend client, and static consistency of compose, Prometheus, Grafana and code.

Likely trouble spots:
- **Model image build fails on pip pins:** rebuild with your venv's Python version:
  `docker compose build --build-arg PYTHON_VERSION=3.13 model-server`
- **Backend returns 503:** `docker compose logs model-server`; usually a pin or schema problem.
- **Grafana panels blank in the console page:** open http://localhost:3000 directly first; embedding needs
  the `GF_SECURITY_ALLOW_EMBEDDING` and anonymous-viewer settings already in the compose file.
- **mlflow-ui cannot show artifacts:** the `${PWD}/mlartifacts` mount needs `docker compose` run from the
  project root on Linux/macOS.
