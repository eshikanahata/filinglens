# FilingLens: System Test Checklist

Run these on your machine with the stack up (`docker compose up -d`, wait about 40 seconds).
For each test: follow the steps, compare with **Expected**, tick **Pass** or **Fail**, and save the
evidence file named in **Evidence** into `docs/screenshots/` (create the folder first).
Do the tests in this order: the last ones change state (stop services, retrain) and are placed last
on purpose.

Tip for screenshots: Linux `PrtSc` or `Shift+PrtSc` (select area). Crop to the relevant part.

## Results summary (fill in)

| ID | Title | Result |
|---|---|---|
| ST-01 | Start everything with one command | |
| ST-02 | Analyse a company | |
| ST-03 | History view | |
| ST-04 | Invalid and unknown tickers | |
| ST-05 | Help page and responsive layout | |
| ST-06 | Pipeline console | |
| ST-07 | Prometheus target and alert rules | |
| ST-08 | Metrics change with traffic | |
| ST-09 | Grafana dashboard | |
| ST-10 | DVC pipeline is reproducible | |
| ST-11 | Experiment tracking in MLflow | |
| ST-12 | Model registry matches what is served | |
| ST-13 | Result traceable to a Git commit | |
| ST-14 | Parse success and exclusions | |
| ST-15 | Ray speed-up | |
| ST-16 | Latency target | |
| ST-17 | Containers run as non-root | |
| ST-18 | No drift on real data | |
| ST-19 | Model server outage | |
| ST-20 | Backend outage | |
| ST-21 | Drift detected and retraining triggered | |
| ST-22 | Rollback of a worse model | |
| ST-23 | Reset to real drift result | |

---

## ST-01 Start everything with one command
**Steps:** `docker compose down`, then `docker compose up -d`, wait 40 seconds, then `docker compose ps`.
**Expected:** six services running; `model-server`, `backend` and `frontend` show `(healthy)`.
**Evidence:** paste the `docker compose ps` output into `docs/screenshots/compose_ps.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-02 Analyse a company
**Steps:** open http://localhost:8501, choose **AAPL** in the company box.
**Expected:** a coloured risk signal, an estimated chance as a percentage with a bar, the filing date and the
date it is compared with, one to four "what stands out" sentences, six change figures, two topic lists, the
disclaimer at the bottom.
**Evidence:** `ui_analysis.png`
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-03 History view
**Steps:** on the AAPL result, open **Signal across this company's filings**.
**Expected:** a table of filings, oldest first; the oldest shows "Not enough data" with an empty score; later rows
show a signal and score; a line chart appears when at least two filings have scores.
**Evidence:** `ui_history.png`
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-04 Invalid and unknown tickers
**Steps:**
```bash
curl -s -w "  -> HTTP %{http_code}\n" localhost:8000/analysis/ZZZZ
curl -s -w "  -> HTTP %{http_code}\n" localhost:8000/analysis/12345
curl -s -w "  -> HTTP %{http_code}\n" "localhost:8000/analysis/AA;DROP"
```
**Expected:** 404 `unknown_ticker`, 400 `invalid_input`, 400 `invalid_input`; each with a short plain message and
no word "Traceback".
**Evidence:** paste the output into `docs/screenshots/invalid_inputs.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-05 Help page and responsive layout
**Steps:** (a) open **How to use** in the sidebar. (b) On the analysis page press `F12`, switch on the browser's
device toolbar, and choose a phone width (about 390 pixels).
**Expected:** (a) readable help text. (b) content stacks into one column and stays readable; nothing is cut off
or overlapping.
**Evidence:** `ui_mobile.png`
**Result:** [ ] Pass  [ ] Fail   **Notes (describe anything awkward):**

## ST-06 Pipeline console
**Steps:** open **Pipeline console** after a few analyses (so the monitoring panels have data).
**Expected:** parse success rate, throughput, failed filings, serving model; stage table with statuses; Ray
chart; model comparison; drift section; recent events (may be empty before ST-21); four Grafana panels showing
graphs.
**Evidence:** `console_stages.png` (top half) and `console_grafana.png` (monitoring panels)
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-07 Prometheus target and alert rules
**Steps:** open http://localhost:9090/targets and http://localhost:9090/alerts.
**Expected:** target `filinglens-backend` is **UP**; six alert rules are listed (BackendDown, ModelServerErrors,
HighServerErrorRate, SlowResponses, ParseSuccessBelowTarget, DataDriftDetected), all inactive.
**Evidence:** `prometheus_targets.png`, `prometheus_alerts.png`
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-08 Metrics change with traffic
**Steps:**
```bash
M='curl -s localhost:8000/metrics | grep "^filinglens_http_requests_total" | grep -F "/analysis/{ticker}" | grep -F "200"'
eval $M
for t in AAPL MSFT NVDA; do curl -s -o /dev/null localhost:8000/analysis/$t; done
eval $M
```
**Expected:** the counter printed the second time is exactly 3 higher than the first.
**Evidence:** paste both outputs into `docs/screenshots/metrics_counter.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-09 Grafana dashboard
**Steps:** open http://localhost:3000 (login `admin` / `admin`), Dashboards, **FilingLens**.
**Expected:** the dashboard loads with its panels (request rate, latency, model server calls, analyses by signal,
parse success, throughput, filings by stage, champion AUC, Ray speed-up, drift detected, PSI by feature,
pipeline events). Panels fed by recent traffic show data.
**Evidence:** `grafana_dashboard.png`
**Result:** [ ] Pass  [ ] Fail   **Notes (list any panel showing No data):**

## ST-10 DVC pipeline is reproducible
**Steps:** `dvc status`, then `dvc dag > docs/screenshots/dvc_dag.txt`, then `cat docs/screenshots/dvc_dag.txt`.
**Expected:** `dvc status` says data and pipelines are up to date; the graph lists the stages download, parse,
prices, labels, features, train, drift, serving_data, export_model.
**Evidence:** `dvc_dag.txt`
**Result:** [ ] Pass  [ ] Fail   **Notes (if status shows changes, paste them):**

## ST-11 Experiment tracking in MLflow
**Steps:** open http://localhost:5000, experiment **filinglens**, open one run (for example the XGBoost run).
**Expected:** runs exist for majority_baseline, logistic_regression and xgboost; a run shows parameters, metrics
(test and cross-validation), artifacts (model, feature importances, predictions) and tags including `git_commit`,
`features_sha256` and `labels_sha256`.
**Evidence:** `mlflow_runs.png` (run list) and `mlflow_run_detail.png` (one run)
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-12 Model registry matches what is served
**Steps:** in MLflow open **Models**, **filinglens-risk**. Then run:
```bash
cat models/champion_info.json
curl -s localhost:8000/analysis/AAPL | python -c "import sys,json; print(json.load(sys.stdin)['model'])"
```
**Expected:** versions are listed; alias `champion` points at one version; that version equals both the `version`
in `champion_info.json` and the `version` the API reports.
**Evidence:** `mlflow_registry.png` plus the two printed outputs in `docs/screenshots/served_model.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-13 Result traceable to a Git commit
**Steps:**
```bash
cat reports/train_run.json
git cat-file -t $(python -c "import json; print(json.load(open('reports/train_run.json'))['git_commit'])")
```
**Expected:** `train_run.json` has `git_commit`, `champion_run_id`, `features_sha256`, `labels_sha256`; the Git
command prints `commit`.
**Evidence:** paste into `docs/screenshots/traceability.txt`. Note whether `git_dirty` is True.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-14 Parse success and exclusions
**Steps:** `cat reports/parse_metrics.json`, `wc -l reports/parse_failures.csv`, `grep -i excluded config/tickers.txt`.
**Expected:** `success_rate` is 1.0 and `filings_total` is 290; the failures file has only its header line (1 line);
four excluded companies are listed with reasons.
**Evidence:** paste into `docs/screenshots/parse_evidence.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-15 Ray speed-up
**Steps:** `cat reports/ray_benchmark.json`
**Expected:** speed-up above 1.0 for 2, 4 and 8 workers (earlier measurement: 1.84, 2.99, 4.68).
**Evidence:** `docs/screenshots/ray_benchmark.json` (copy the file).
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-16 Latency target
**Steps:** `python scripts/measure_latency.py` (stack running, nothing else heavy open).
**Expected:** zero errors, and the 95th percentile of `GET /analysis/{ticker}` below 1000 ms; the script prints
MET.
**Evidence:** `reports/latency_report.json` and the printed table.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-17 Containers run as non-root
**Steps:** `docker compose exec backend id -u` and `docker compose exec frontend id -u`.
**Expected:** neither prints `0`.
**Evidence:** paste into `docs/screenshots/nonroot.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes (the model server runs as root: known limitation):**

## ST-18 No drift on real data
**Steps:** `dvc repro drift` then `cat reports/drift_metrics.json`.
**Expected:** `drift_detected` is 0 and `simulated` is 0 (earlier result: 1 of 14 features drifted, below the
25% threshold).
**Evidence:** paste into `docs/screenshots/drift_real.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-19 Model server outage  (changes state, put it near the end)
**Steps:**
1. `docker compose stop model-server`
2. In the app, analyse any company. Then `curl -s localhost:8000/health`.
3. Wait about 90 seconds, open http://localhost:9090/alerts.
4. `docker compose start model-server`, wait until `docker compose ps` shows it healthy, analyse again.
**Expected:** step 2: the app shows "The scoring service is temporarily unavailable" and `/health` reports
`degraded` and `model_server: down`; step 3: **ModelServerErrors** is pending or firing; step 4: analysis works
again.
**Evidence:** `ui_error_model_down.png`, `prometheus_alert_model.png`
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-20 Backend outage  (changes state)
**Steps:** `docker compose stop backend`, reload http://localhost:8501 and try to analyse a company; wait about
90 seconds and look at http://localhost:9090/alerts; then `docker compose start backend`.
**Expected:** the app shows "We can't reach the analysis service right now"; **BackendDown** becomes pending or
firing; after the restart everything works again (the frontend needs no restart).
**Evidence:** `ui_error_backend_down.png`
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-21 Drift detected and retraining triggered  (changes state)
**Steps:**
```bash
python -m src.drift.retrain --simulate-shift
tail -n 6 reports/run_history.jsonl
docker compose up -d --force-recreate model-server backend
```
Then open the **Pipeline console** and http://localhost:9090/alerts (wait about two minutes).
**Expected:** the command prints `drift_detected: true`, `retrained: true`, a `decision` and the versions; the
event log shows `drift_check` (status drift), `retrain_started`, `model_promoted` (or `model_rollback`), and
`model_exported`; the console shows the drift table with a yellow "deliberately shifted" notice and the events;
**DataDriftDetected** goes pending, then firing; analysis still works after the restart.
**Evidence:** `console_drift.png`, `prometheus_alert_drift.png`, and the printed JSON plus event log lines in
`docs/screenshots/retrain_run.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-22 Rollback of a worse model  (changes state)
**Steps:**
1. Note the current version: `grep version models/champion_info.json`
2. In `params.yaml` change `promotion_tolerance: 0.01` to `promotion_tolerance: -1.0` (demo only: it makes every
   new model look worse).
3. `python -m src.drift.retrain --force`
4. `tail -n 5 reports/run_history.jsonl` and `grep version models/champion_info.json`
5. **Put `promotion_tolerance` back to `0.01`.**
**Expected:** `decision` is `rollback`; the event log has `model_rollback` with `rejected_version` and
`restored_version`; the served version in step 4 equals the one from step 1.
**Evidence:** `docs/screenshots/rollback_run.txt`
**Result:** [ ] Pass  [ ] Fail   **Notes:**

## ST-23 Reset to real drift result
**Steps:** `dvc repro drift`, then `cat reports/drift_metrics.json`, then
`docker compose up -d --force-recreate model-server backend`.
**Expected:** `simulated` is 0 again; the console no longer shows the yellow notice; the alert returns to inactive
after a minute or two.
**Evidence:** paste into `docs/screenshots/drift_reset.txt`.
**Result:** [ ] Pass  [ ] Fail   **Notes:**
