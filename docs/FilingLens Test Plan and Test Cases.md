# FilingLens: Test Plan and Test Cases

Eshika Nahata (DA24B004) | Individual project | Version 1.1

## 1. Purpose and Scope

This plan describes how FilingLens is tested: what is tested, at which level, with what data, how a result is judged, and what counts as acceptable. It lists every automated test module and every manual system test case. The results of running the plan are in the Test Report.

**In scope:** the data pipeline (ingestion, parsing, labels, features), model training and tracking, model export and serving, the backend API, the Streamlit frontend, monitoring (metrics, dashboard, alerts), drift detection, retraining and rollback, and the Docker Compose deployment.

**Out of scope:** the statistical quality of the model as a stock predictor (it is evaluated, not tested; see the Test Report and the High-Level Design), load testing with many concurrent users, and the SEC and price-data websites themselves.

## 2. Test Strategy

| Level | What it checks | How |
| --- | --- | --- |
| Unit | One function or class in isolation: label calculation, text metrics, drift statistics, signal labels, promotion rules | Automated, pytest, small synthetic inputs |
| Integration | Several parts together: pipeline stages end to end, the API with a fake model server, the Streamlit app against a fake backend, the training stage with a real MLflow store, the real model registry's rollback mechanics | Automated, pytest, synthetic data and temporary stores |
| Static configuration | The deployment files agree with each other and with the code: service addresses, ports, mounts, dashboard queries against exported metrics, alert rules, loose coupling | Automated, pytest, reads the files |
| System | The real Docker stack on the real data: start-up, user flows, error handling under outages, monitoring, drift and rollback demonstrations | Manual, using the checklist in section 7 |
| Non-functional | Latency, parsing throughput, container security basics, reproducibility | Scripted and manual (sections 5 and 7) |
| Continuous integration | Code style and the whole automated suite on every change | DVC stages `lint` (flake8) and `test` (pytest), run by `dvc repro` and by a git pre-commit hook; `export_model` depends on the test summary |

**Principles**

- Every behaviour that can be checked without Docker is checked by an automated test, so the whole automated suite runs in under a minute.
- Real components are used instead of mocks wherever it is cheap: a real MLflow store, a real Ray run, a real Streamlit script, and a real MLflow model server in a one-off check.
- A **positive control** guards against a false sense of safety: synthetic data with a planted signal must be learned by the training code, so that a weak result on real filings cannot be a hidden bug.
- Negative cases are tested as carefully as positive ones: invalid input, unknown companies, unreachable services, malformed model replies, missing files, too little data.
- Failures are never hidden. A failed test is recorded with its cause and either fixed or accepted as a documented limitation.
- Tests are isolated from their environment. A shared fixture (`tests/conftest.py`) removes MLflow run variables, so the suite behaves the same under plain `pytest`, under `dvc repro test` and under `mlflow run . -e test`.

## 3. Test Environment

| Item | Value |
| --- | --- |
| Machine | Personal laptop running Linux |
| Python | 3.14 virtual environment for development and tests, pinned in `requirements.lock`; the same versions are built fresh by `mlflow run . -e test` (MLproject) |
| Containers | Docker Compose with seven services: model-server, backend, frontend, prometheus, grafana, mlflow-ui, cadvisor. The application images use Python 3.14 |
| Data | Real: 318 parsed 10-K filings of 54 companies, prices and benchmark from a free source |
| Tools | pytest (with a JUnit report summarised by `scripts/summarize_tests.py`), flake8 and black, DVC (`lint` and `test` stages), MLflow Projects, `scripts/measure_latency.py`, curl, a web browser |

Unit and integration tests do not need the network, Docker, or the real data. System tests need the running stack and the real data.

## 4. Entry and Exit Criteria

**Entry:** code committed through the pre-commit hook (so `lint` and `test` passed); `dvc repro` completed; `docker compose up -d` brings the stack to a healthy state.

**Exit:** the full automated suite has been run and every failure explained; every system test has a recorded result with evidence; every acceptance criterion in section 5 is marked met or not met with the reason; the Test Report is written.

## 5. Acceptance Criteria

These come from the project proposal. Each is judged against evidence, and the outcome is recorded in the Test Report.

| ID | Criterion | How it is verified |
| --- | --- | --- |
| AC-1 | At least 95% of the selected filings parse successfully; failures are logged and visible in the console | `reports/parse_metrics.json`, `reports/parse_failures.csv`, console page (ST-06, ST-14) |
| AC-2 | The Ray pipeline is measurably faster than a single worker | `reports/ray_benchmark.json` (ST-15) |
| AC-3 | The final model beats the majority-class baseline on the time-based test set, with metrics reported honestly | `reports/train_metrics.json`, `reports/test_uncertainty.csv` (ST-11, ST-12) |
| AC-4 | API 95th-percentile latency under 1 second on a local machine | `scripts/measure_latency.py` (ST-16) |
| AC-5 | The drift check detects a deliberately shifted batch and triggers retraining | automated drift and retrain tests; ST-21 |
| AC-6 | All services start with a single `docker compose up` | ST-01 |
| AC-7 | Unit tests pass, with a test report giving the number of cases passed and failed | pytest JUnit summary |
| AC-8 | The code follows a standard Python style: flake8 reports no warnings | `reports/lint_report.txt` from the `lint` stage (ST-26) |

## 6. Automated Test Inventory

The suite contains **130** automated tests in 24 modules. The count per module is taken from the JUnit report.

| Module | Tests | Level | What it verifies |
| --- | --- | --- | --- |
| `test_edgar_client` | 8 | Unit | Selection of 10-K filings by form type and date window; filings in EDGAR's older submission pages are found and duplicates removed; without those pages old filings are missed; pages that end before the window are not fetched; filing URL building; the User-Agent contact is required and placeholder values are rejected; the contact is read from a `.env` file |
| `test_section_extractor` | 5 | Unit | Item 1A is extracted rather than the table of contents or cross-references; filings with only a table of contents fail cleanly; hidden inline-XBRL header text is removed; a heading split across formatting tags is still found |
| `test_parse_pipeline` | 1 | Integration | Ray parses real files end to end; failures are returned as data and counted, not raised |
| `test_labels` | 6 | Unit | Abnormal-return label for under- and out-performers; base date is the last trading day on or before the filing; recent filings stay unlabeled; filings before the price history and price gaps are unlabeled |
| `test_text_metrics` | 8 | Unit | Tokenising; sentiment word shares; empty text; syllable counting; readability ordering; loading the word-list file and its error messages for a missing file or missing columns |
| `test_features_pairing` | 2 | Unit | Each filing is paired with the filing about one year earlier only; pairing never crosses companies |
| `test_pipeline_integration` | 1 | Integration | Labels and features stages run end to end on synthetic filings and prices; the first filing has no year-over-year features; similarity is between 0 and 1 |
| `test_dataset_split` | 3 | Unit | The split is time-ordered with an embargo and no overlap; unlabeled and no-prior filings are excluded; a too-small split raises an error |
| `test_train_smoke` | 1 | Integration | The training stage runs with a real MLflow store, logs three runs with tags and metrics, registers the champion and sets its alias |
| `test_positive_control` | 3 | Integration | Logistic regression and XGBoost both recover a planted signal (AUC above 0.8); bootstrap intervals separate signal from noise |
| `test_export_model` | 3 | Integration | The exported model loads from a plain folder and returns class probabilities; the model description file is built correctly; the checksum file matches the model file |
| `test_eda` | 4 | Unit and integration | Missing years are counted only inside a company's run; outlier share; a planted feature-label signal is found and the noise band is correct; the report is built end to end and flags a company with few filings |
| `test_serving_data` | 2 | Unit | Percentile ranks only among filings with a prior year; changed-term detection |
| `test_explain` | 5 | Unit | Signal labels at their thresholds; unusual changes are selected, ordered and capped at four; a fallback statement when nothing stands out; statements never contain nested parentheses |
| `test_model_client_contract` | 2 | Unit | The number of predictions must equal the number of rows sent |
| `test_api` | 11 | Integration | Every endpoint with a fake model server: health when the model is up and down; tickers; scored and unscored analysis; unknown and invalid tickers; friendly 503; history uses one batched model call; pipeline endpoint; exported metrics; fail-fast when data is missing; probabilities versus class labels |
| `test_frontend` | 4 | Unit | Display formatting helpers; the client uses the configured address; backend errors become friendly messages; an unreachable backend never leaks an address |
| `test_frontend_app` | 3 | Integration | The real Streamlit script against a fake backend: analysis page, console page, and a friendly message when the backend is down |
| `test_drift` | 11 | Unit and integration | PSI behaviour including empty and constant inputs; no drift for the same distribution; drift for a shifted batch; both PSI and KS are required; the share rule; the shift simulator; period selection; the drift stage end to end including the event log |
| `test_retrain_cli` | 2 | Unit | The promotion tolerance comes from the parameter file by default; the `--tolerance` option overrides it, including negative values |
| `test_git_info` | 5 | Unit | A clean tree is not dirty; outputs deleted by DVC do not count as dirty; changed or new source and configuration files do; outside a Git repository the commit is reported as unknown |
| `test_retrain` | 8 | Unit and integration | Promotion rule including missing scores; no drift means no retraining; drift triggers retraining and promotion of a better model; a worse model is rolled back; forced retraining; the event log; the real MLflow registry's champion alias and rollback |
| `test_phase4_wiring` | 9 | Integration and static | Drift and events appear in the pipeline endpoint and in the metrics; missing drift files are tolerated; alert rules use only exported metrics; Prometheus loads the mounted rules; dashboard panels exist; the console shows drift and events; the drift stage is wired correctly |
| `test_deploy_config` | 23 | Static | Expected services; separate frontend and backend images; the frontend never knows the model server address; ports do not collide; read-only mounts match configuration; start-up waits for health; Prometheus and Grafana point at the right services; dashboard queries use exported metrics; the backend image has no machine-learning libraries; the API never imports training code; all three application images run as a non-root user; the model server verifies the checksum before serving; no hard-coded Grafana password; every container is monitored (cAdvisor service and scrape job) |

In addition, a one-off script (`scripts/check_serving_contract.py`) starts a real MLflow model server and checks that the backend's client receives probabilities identical to the local model for both model types.

## 7. Manual System Test Cases

The detailed steps, exact commands and result boxes are in `docs/system_test_checklist.md`. Results and evidence are in the Test Report.

| ID | Area | Objective | Expected result |
| --- | --- | --- | --- |
| ST-01 | Deployment | Start everything with one command | Seven services running; model-server, backend and frontend healthy |
| ST-02 | UI | Analyse a company | Signal, score bar, dates, what stands out, six changes, topics, disclaimer |
| ST-03 | UI | History view | Oldest filing is Not enough data; later rows scored; chart shown |
| ST-04 | Input handling | Unknown and invalid tickers | 404 and 400 with short plain messages, no stack trace |
| ST-05 | UI | Help page and phone-width layout | Readable; one column; nothing cut off |
| ST-06 | Console | Pipeline console | Metrics, stage table, Ray chart, model comparison, drift, events, four live panels |
| ST-07 | Monitoring | Prometheus targets and alert rules | Three targets up (backend, cadvisor, prometheus); eight alert rules loaded and inactive |
| ST-08 | Monitoring | Metrics change with traffic | Request counter rises by exactly the number of requests made |
| ST-09 | Monitoring | Grafana dashboard | Dashboard loads; panels show data, including CPU and memory for every container |
| ST-10 | Reproducibility | DVC pipeline | Status up to date; graph shows all stages |
| ST-11 | Experiment tracking | MLflow runs | Three model runs with parameters, metrics, artifacts, commit and data-hash tags |
| ST-12 | Registry | Registry matches what is served | Alias version equals the version in the model file and in the API |
| ST-13 | Reproducibility | Result traceable to a commit | The training run's commit exists in Git |
| ST-14 | Data pipeline | Parse success and exclusions | 100% on the 318 selected filings; five exclusions documented |
| ST-15 | Performance | Ray speed-up | Speed-up above 1 at 2, 4 and 8 workers |
| ST-16 | Performance | Latency | No errors; 95th percentile under 1 second |
| ST-17 | Security | Containers run as non-root | Model-server, backend and frontend user id is not 0 |
| ST-18 | Drift | No drift on real data | Drift flag 0, not simulated |
| ST-19 | Resilience | Model server outage | Friendly message; health degraded; alert fires; recovery after restart |
| ST-20 | Resilience | Backend outage | Friendly message; alert fires; recovery without restarting the frontend |
| ST-21 | Drift and retraining | Deliberate shift is detected and triggers retraining | Event log records the full cycle; console and alert show drift |
| ST-22 | Rollback | A worse model is rolled back | Rollback event; served version unchanged |
| ST-23 | Drift | Reset to the real result | Not simulated again; alert clears |
| ST-24 | Security | A tampered model is refused | After changing the model file, the model server logs a checksum failure and does not serve; restoring with `dvc checkout` recovers it |
| ST-25 | Monitoring | Container-down alert | Stopping the model-server container makes `ModelServerContainerDown` fire; it clears after a restart |
| ST-26 | Continuous integration | Lint and tests gate commits and the model export | `dvc repro lint test` passes with 0 flake8 warnings; a commit with a lint error is blocked by the hook; `dvc dag` shows `lint` → `test` → `export_model` |
| ST-27 | Reproducibility | Tests in a fresh environment | `mlflow run . -e test` builds an environment from `python_env.yaml` and `requirements.lock`, and all tests pass |

## 8. Requirements Traceability

| Requirement | Automated tests | System tests |
| --- | --- | --- |
| R1 Download and parse filings robustly | `test_edgar_client`, `test_section_extractor`, `test_parse_pipeline` | ST-14, ST-15 |
| R2 Labels use no future information | `test_labels`, `test_dataset_split` | none |
| R3 Features are correct and leakage-free | `test_text_metrics`, `test_features_pairing`, `test_pipeline_integration` | none |
| R4 Models are trained, tracked and reproducible | `test_train_smoke`, `test_positive_control`, `test_git_info` | ST-11, ST-13, ST-27 |
| R5 The model is served over REST as probabilities | `test_export_model`, `test_model_client_contract`, `test_api` | ST-12 |
| R6 A usable interface with friendly errors | `test_frontend`, `test_frontend_app`, `test_explain` | ST-02 to ST-05, ST-19, ST-20 |
| R7 Loose coupling of frontend, backend and model | `test_deploy_config`, `test_api` | none |
| R8 Monitoring and alerting | `test_api`, `test_deploy_config`, `test_phase4_wiring` | ST-07 to ST-09, ST-25 |
| R9 Drift detection, retraining and rollback | `test_drift`, `test_retrain`, `test_retrain_cli`, `test_phase4_wiring` | ST-18, ST-21 to ST-23 |
| R10 Pipeline visibility console | `test_frontend_app`, `test_phase4_wiring` | ST-06 |
| R11 Performance | none | ST-15, ST-16 |
| R12 One-command deployment | `test_deploy_config` | ST-01 |
| R13 Security: input validation, least privilege, secrets, model integrity | `test_api`, `test_edgar_client`, `test_deploy_config`, `test_export_model` | ST-04, ST-17, ST-24 |
| R14 Continuous integration and environment parity | `test_deploy_config` (pipeline stages), the `lint` and `test` stages themselves | ST-26, ST-27 |

## 9. Test Data

- **Unit and integration tests** use small synthetic filings, prices and feature tables generated in the tests, plus temporary MLflow stores and temporary files. They need no network and leave no state behind.
- **The positive control** uses synthetic features with a planted relationship to the target.
- **System tests** use the real dataset: 318 parsed filings of 54 companies, with prices from the free source and the SPY benchmark.
- **Deliberately shifted data** for the drift demonstration is produced by a built-in simulator that moves every feature by 1.5 reference standard deviations, and the report is marked simulated.

## 10. Defects and Reporting

Each failed test is recorded in the Test Report with: what happened, the cause, the fix or the decision to accept it, and the test that now guards against it. Problems found during development are listed too, because they show what the tests are for. Examples already found and fixed: the section extractor ran past its end marker; a training parameter clashed with MLflow's automatic logging; the backend silently accepted fewer model scores than rows.

## 11. Limitations of the Testing

- The model's predictive quality cannot be unit-tested. It is evaluated with a time-based split and reported with confidence intervals; the acceptance criterion on beating the baseline is judged on that evidence.
- Parsing success of 100% applies to the 318 selected filings after excluding four companies with non-standard layouts (and one with no 10-K in the window). It does not claim the extractor handles every filing layout.
- Latency is measured with one client making sequential requests on the same machine. It is not a load test.
- The Docker deployment, Grafana rendering and alert behaviour are checked manually, because they need the real stack.
- Alerts are evaluated by Prometheus but not delivered anywhere, so testing checks that they fire, not that they notify.
