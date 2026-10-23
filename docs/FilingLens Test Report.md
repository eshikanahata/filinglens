# FilingLens: Test Report

Eshika Nahata (DA24B004) | Individual project | Version 1.1

This report gives the results of running the Test Plan. Evidence files are in `docs/screenshots/` and `reports/`.

## 1. Summary

- **Automated tests:** 126 tests in 23 modules, all passing. The first full run, before the fixes described in section 9, had 108 tests, all passing. The suite now runs as the DVC `test` stage, on every commit through a git hook, and in a fresh environment through `mlflow run . -e test`.
- **Code style:** flake8 reports 0 warnings (maximum line length 120); the code is formatted with black. This is enforced by the DVC `lint` stage.
- **Manual system tests:** 27 cases. Of the original 23, eighteen passed on the first attempt and five needed attention (ST-05 not run at first, ST-06 incomplete, ST-10 failed, ST-21 partial, ST-22 failed); all were fixed or completed. Four cases (ST-24 to ST-27) were added with the security, monitoring and CI improvements. **All 27 now pass.**
- **Acceptance criteria:** seven of eight are met. **AC-3 is not met:** the final model cannot be distinguished from the majority-class baseline (section 5 and 7).
- **Problems found and resolved:** twenty-one, listed in section 9. They include a mistake in the deployment instructions, an unclean pipeline status, a rollback that did not trigger, a reproducibility flag that was wrong, and a download bug that silently missed older filings for twelve companies.

## 2. Scope and Environment

The test scope, levels and strategy are in the Test Plan. Environment: a personal Linux laptop, a Python 3.14 virtual environment pinned in `requirements.lock`, Docker Compose with seven services (application images on Python 3.14), and the real dataset of 318 parsed filings from 54 companies (290 before the download fix in defect 15). The first full system run was on 17 October 2026. Tests that failed or were incomplete were re-run after the fixes in section 9.

## 3. Automated Test Results

Final run: **126 passed, 0 failed, 0 skipped**.

| Test module | Passed | Failed | Skipped |
| --- | --- | --- | --- |
| test\_api | 11 | 0 | 0 |
| test\_dataset\_split | 3 | 0 | 0 |
| test\_deploy\_config | 23 | 0 | 0 |
| test\_drift | 11 | 0 | 0 |
| test\_edgar\_client | 8 | 0 | 0 |
| test\_explain | 5 | 0 | 0 |
| test\_export\_model | 3 | 0 | 0 |
| test\_features\_pairing | 2 | 0 | 0 |
| test\_frontend | 4 | 0 | 0 |
| test\_frontend\_app | 3 | 0 | 0 |
| test\_git\_info | 5 | 0 | 0 |
| test\_labels | 6 | 0 | 0 |
| test\_model\_client\_contract | 2 | 0 | 0 |
| test\_parse\_pipeline | 1 | 0 | 0 |
| test\_phase4\_wiring | 9 | 0 | 0 |
| test\_pipeline\_integration | 1 | 0 | 0 |
| test\_positive\_control | 3 | 0 | 0 |
| test\_retrain | 8 | 0 | 0 |
| test\_retrain\_cli | 2 | 0 | 0 |
| test\_section\_extractor | 5 | 0 | 0 |
| test\_serving\_data | 2 | 0 | 0 |
| test\_text\_metrics | 8 | 0 | 0 |
| test\_train\_smoke | 1 | 0 | 0 |
| **Total (126)** | **126** | **0** | **0** |

The first full run (108 tests, all passing) is the same table without `test_git_info`, `test_retrain_cli`, one test in `test_explain`, three tests in `test_edgar_client`, one in `test_export_model` and six in `test_deploy_config`. Those eighteen tests were added after testing and review exposed the problems in section 9, so each one guards against a real defect or gap that was found.

**Code style.** `flake8 api frontend src tests scripts` reports 0 warnings (`reports/lint_report.txt`). Before the style configuration was added, flake8 reported 28 warnings (unused imports, several imports on one line, ambiguous variable names, long lines) and black would have reformatted 59 files; all were fixed.

**Fresh environment.** `mlflow run . -e test` built a new Python 3.14.4 environment from `python_env.yaml` and `requirements.lock` and ran the full suite: all tests passed (`mlproject_test.png`).

The suite also emits deprecation warnings from the date arithmetic in pandas and from MLflow internals on Python 3.14. None affects results.

## 4. Manual System Test Results

Evidence file names refer to `docs/screenshots/`.

| ID | Test | First run | Final | Evidence and notes |
| --- | --- | --- | --- | --- |
| ST-01 | Start everything with one command | Pass | Pass | `compose_ps.png`: all services running; model-server, backend and frontend healthy (the others have no health check defined). Re-run with seven services after cAdvisor was added |
| ST-02 | Analyse a company | Pass | Pass | `ui_analysis.png`: signal, score bar, dates, statements, six changes, disclaimer. Cosmetic issues found and fixed (section 9) |
| ST-03 | History view | Pass | Pass | `ui_history.png`: five filings; the oldest shows Not enough data; the rest are scored; chart shown |
| ST-04 | Invalid and unknown tickers | Pass | Pass | `invalid_inputs.png`: 404 unknown\_ticker, 400 invalid\_input twice; plain messages, no stack trace |
| ST-05 | Help page and phone-width layout | Not run | Pass | `ui_mobile.png`: no layout problems noted |
| ST-06 | Pipeline console | Incomplete | Pass | First run: the stage table had no drift row because the containers were running old code (defect 10). After rebuilding: drift row, drift section and events shown. `console_stages.png`, `console_grafana.png` |
| ST-07 | Prometheus targets and alert rules | Pass | Pass | `prometheus_targets.png`: backend, cadvisor and prometheus targets UP. `prometheus_alerts.png`: eight rules, all inactive |
| ST-08 | Metrics change with traffic | Pass | Pass | `metrics_counter.png`: request counter rose from 1 to 4 after exactly three requests |
| ST-09 | Grafana dashboard | Pass | Pass | `grafana_dashboard.png`: panels show data. Cosmetic issues fixed (defect 14). `grafana_containers.png`: CPU and memory for every container |
| ST-10 | DVC pipeline is reproducible | Fail | Pass | First run: `dvc status` listed changes and `dvc dag` showed two extra nodes from a stale `phase_1_files` folder (defect 11). After removing the folder, status reports everything up to date |
| ST-11 | Experiment tracking in MLflow | Pass | Pass | `mlflow_runs.png`: 12 runs (three models in each of four training cycles at the time); `mlflow_run_detail.png`: metrics logged |
| ST-12 | Registry matches what is served | Pass | Pass | `mlflow_registry.png`: alias champion on version 4; `served_model.png`: model file version 4; the application reported version 4 |
| ST-13 | Result traceable to a Git commit | Pass with caveat | Pass | `traceability.png`: the commit exists in Git. The first run recorded `git_dirty = True` (defect 13). After the fix and a retrain from a clean commit, `reports/train_run.json` shows `git_dirty = False` |
| ST-14 | Parse success and exclusions | Pass | Pass | `parse_evidence.png`: 318 of 318 parsed (290 of 290 before the download fix); failure file has only its header; five exclusions documented |
| ST-15 | Ray speed-up | Pass | Pass | `ray_benchmark.png`: 1.84x, 2.99x, 4.68x at 2, 4, 8 workers |
| ST-16 | Latency target | Pass | Pass | `latency_report.png`: 0 errors; p95 18.9 ms against a 1000 ms target |
| ST-17 | Containers run as non-root | Pass | Pass | `nonroot.png`: model-server, backend and frontend run as user 1000. At first only backend and frontend were checked; the model server ran as root (defect 20) |
| ST-18 | No drift on real data | Pass | Pass | `drift_real.png`: 1 of 14 features drifted; no batch drift; not simulated |
| ST-19 | Model server outage | Pass | Pass | `ui_error_model_down.png`: friendly message; `prometheus_alert_model.png`: ModelServerErrors firing |
| ST-20 | Backend outage | Pass | Pass | `ui_error_backend_down.png`: friendly message |
| ST-21 | Drift detected and retraining triggered | Partial | Pass | First run: the retraining cycle was recorded in the event log, but the console drift section and the DataDriftDetected alert were not shown, because the containers were running old code (defect 10). After rebuilding, the console and the alert showed the drift |
| ST-22 | Rollback of a worse model | Fail | Pass | First run: the decision was promote, not rollback, because the tolerance edit had not taken effect (defect 12). After adding a `--tolerance` command-line option, the run printed a rollback decision |
| ST-23 | Reset to real drift result | Pass | Pass | `drift_reset.png`: simulated back to 0 |
| ST-24 | Tampered model is refused | Pass | Pass | `checksum_refused.png`: after one byte was appended to `model.pkl`, the model server logged `model.pkl: FAILED` and did not serve; `dvc checkout models/champion` restored it |
| ST-25 | Container-down alert | Pass | Pass | `alert_container_down.png`: with the model-server container stopped, `ModelServerContainerDown` fired; it cleared after a restart |
| ST-26 | Lint and tests gate commits and the model export | Pass | Pass | `ci_pass.png`: `dvc repro lint test` passed with 0 flake8 warnings. `ci_blocked_commit.png`: a commit with an unused import was blocked by the hook. `dvc_dag.png`: `lint` → `test` → `export_model` |
| ST-27 | Tests in a fresh environment | Fail | Pass | `mlproject_test.png`. First runs failed: pyenv was missing, the lock file pinned a PyTorch build that exists only on PyTorch's own index (defect 17), and one test picked up the MLflow run created by `mlflow run` (defect 18). After the fixes, all tests passed |

## 5. Acceptance Criteria

| ID | Criterion | Result | Evidence |
| --- | --- | --- | --- |
| AC-1 | At least 95% of selected filings parse; failures logged and visible | **Met** on the selected filings | 318 of 318 (100%) after excluding four companies with non-standard layouts and one with no 10-K in the window. The first run on all companies, before the download fix, reached 281 of 314 (89.5%), so the exclusions are material and are documented |
| AC-2 | Ray is faster than one worker | **Met** | 77.1 filings per minute with one worker; 360.6 with eight (4.68x) |
| AC-3 | Final model beats the majority-class baseline | **Not met** | Champion test accuracy 51.7% equals the baseline; test AUC 0.44 with a 95% interval of 0.30 to 0.60 (section 7) |
| AC-4 | API 95th percentile latency under 1 second | **Met** | 18.9 ms (19.3 ms in an earlier run), zero errors |
| AC-5 | Drift check detects a deliberately shifted batch and triggers retraining | **Met** | 14 of 14 features drifted (largest PSI 8.23); retraining started and completed; automated tests cover the same path |
| AC-6 | All services start with one `docker compose up` | **Met** | Seven services started; the data and model folders it mounts must first exist from `dvc repro` |
| AC-7 | Unit tests pass, with counts reported | **Met** | 126 of 126 passed |
| AC-8 | flake8 reports no warnings | **Met** | 0 warnings (`reports/lint_report.txt`), enforced by the `lint` stage |

## 6. Performance Results

**API latency** (`scripts/measure_latency.py`; one client, sequential requests, same machine; 54 companies, three repeats)

| Endpoint | Requests | Errors | p50 (ms) | p95 (ms) | Max (ms) |
| --- | --- | --- | --- | --- | --- |
| GET /health | 30 | 0 | 7.4 | 8.1 | 8.2 |
| GET /tickers | 30 | 0 | 4.1 | 5.0 | 5.4 |
| GET /analysis/{ticker} | 162 | 0 | 17.2 | 18.9 | 19.8 |
| GET /analysis/{ticker}/history | 162 | 0 | 16.9 | 18.5 | 20.2 |
| GET /pipeline/runs | 30 | 0 | 5.4 | 6.1 | 6.8 |

This is a check of the latency criterion, not a load test. It says nothing about many simultaneous users.

**Parsing throughput** (Ray benchmark, measured on the 290 filings available before the download fix)

| Workers | Filings per minute | Speed-up |
| --- | --- | --- |
| 1 | 77.1 | 1.00x |
| 2 | 141.5 | 1.84x |
| 4 | 230.4 | 2.99x |
| 8 | 360.6 | 4.68x |

The production parsing run on all 318 filings with four workers processed 263.1 filings per minute. Efficiency falls as workers increase (92%, 75%, 58%), which is typical when workers share disk and memory bandwidth and some cores are hyper-threads. The cause was not measured separately.

## 7. Model Evaluation Results

Time-based split: 202 training filings, 58 test filings, with a 45-day embargo. (Before the download fix: 175 and 57.)

| Model | CV ROC-AUC | Test ROC-AUC (95% interval) | Test accuracy (95% interval) |
| --- | --- | --- | --- |
| Majority baseline | 0.50 | 0.50 | 51.7% (39.7 to 65.5) |
| Logistic regression (champion) | 0.48 | 0.44 (0.30 to 0.60) | 51.7% (39.6 to 63.8) |
| XGBoost | 0.44 | 0.50 (0.35 to 0.66) | 55.2% (41.4 to 67.2) |

**Interpretation.** No model can be distinguished from chance on this data, in cross-validation or on the held-out period. A positive-control test shows the training code recovers a planted signal, so the weak result reflects the data, not a code defect. The champion, logistic regression, was chosen by cross-validation (0.48 against XGBoost's 0.44); both are below 0.5 and the margin is within noise. XGBoost scores higher on the test period (0.50 against 0.44), but the champion is never chosen by test score, and the difference is within noise too. Before the download fix, with 175 training filings, XGBoost was the champion with a test AUC of 0.48; the conclusion is the same with the larger dataset.

**No further tuning.** The models were deliberately not tuned further: with 58 test filings, any improvement found by trying variants against the test set would be luck. In the earlier run, the XGBoost champion reached a training ROC-AUC of 0.98 against a test AUC of 0.48, so a more flexible model mainly memorises the training filings.

**Determinism.** Retraining on unchanged data produced a model with exactly the same cross-validation score every time, which confirms that the seeds are fixed and that the pipeline is reproducible.

## 8. Drift, Retraining and Rollback Results

**Real data.** Comparing 60 recent filings with 202 training-period filings, 1 of 14 features (7%) was flagged, below the 25% batch threshold, so no retraining was triggered; the largest PSI was 0.50. In the run before the download fix (59 against 175 filings) the result was the same, 1 of 14, and three further features had a PSI above 0.2 but failed the KS test: under a PSI-only rule four features (29%) would have triggered retraining. Requiring both tests avoids such false alarms. With 14 features tested at once and a small batch, a single flagged feature can occur by chance.

**Deliberate shift.** The simulated batch drifted on 14 of 14 features (largest PSI 8.23). The orchestrator logged the drift check, started retraining, registered a new version, compared its cross-validation AUC with the previous champion's (identical, because the data had not changed), promoted it, and re-exported the serving folder. A forced retraining without drift behaved the same way.

**Rollback.** With the promotion tolerance set to -1 on the command line, which makes every new model look worse, the orchestrator printed a rollback decision. The previous model version was restored as champion and re-exported.

**Alerts.** ModelServerErrors was observed firing during the model-server outage. DataDriftDetected was observed after the simulated shift once the containers ran the current code.

## 9. Problems Found and Resolved

| # | Found by | Problem | Cause | Resolution and guard |
| --- | --- | --- | --- | --- |
| 1 | Unit test | The section extractor ran past the "Item 1B" marker | Each start was paired with every later end marker | Pair each start with the first end marker after it; tests for table-of-contents and cross-reference cases |
| 2 | First full parse (89.5%) | Microsoft and Oracle filings failed | Text joining split headings across formatting tags ("RIS K FACTORS") | Join text only at block-level tags; regression test for split headings |
| 3 | Diagnostic script | Intel, General Electric, Honeywell and McDonald's filings failed in every year | Annual-report-style filings have no Item 1A heading, only a cross-reference index | Excluded and documented rather than adding fragile per-company rules. Accepted limitation |
| 4 | Smoke test | A parameter name clashed with MLflow's automatic logging | Duplicate parameter name with a different value | Renamed the logged parameter |
| 5 | Smoke test | Model logging was rejected | MLflow 3's default format rejects XGBoost's numpy types | Use the standard pickle-based format; the models are produced and loaded only by this project |
| 6 | System test | The backend returned a 503 for every analysis | The served model returned class labels, not probabilities | Log the model with `predict_proba`; the backend rejects non-probability replies |
| 7 | First start | The experiment browser container tried to pull a local image from a registry | The compose service had no build and no pull policy | `pull_policy: never`; configuration test |
| 8 | Documentation work | The backend silently accepted fewer model scores than rows | Pairing of scores with rows by position | Reject any mismatch with the friendly 503; unit tests |
| 9 | First start | Prometheus could not bind port 9090 | Another monitoring stack on the same machine held the port | Stopped the other stack. Environment issue, not a product defect |
| 10 | ST-06, ST-21 | The console lacked the drift row and the drift alert never fired | Recreating a container restarts the same image; code is baked into images, so new code needs a rebuild | Rebuild with `--build`. The deployment instructions had been wrong and were corrected |
| 11 | ST-10 | `dvc status` was not clean | A leftover `phase_1_files` folder contributed stale stages | Removed the folder; status is clean |
| 12 | ST-22 | The rollback demonstration promoted the model | The tolerance edit in the parameter file had not taken effect | Added a `--tolerance` command-line option; tests; re-run passed |
| 13 | ST-13 | `git_dirty` was always True | DVC deletes a stage's tracked outputs before running it, so the tree always looked dirty | The check now ignores generated paths; tests; a retrain from a clean commit shows `git_dirty = False` |
| 14 | Evidence review | Cosmetic issues: a truncated metric label, doubled parentheses in one statement, and Grafana bars showing successful filings in red | Layout and default colour thresholds | Shorter label, single parentheses, fixed colours; a test checks the statements |
| 15 | Review of download logs | Twelve companies had missing older filings; JPMorgan had only one filing, so no year-over-year comparison was possible | EDGAR lists only about the latest 1,000 filings in a company's "recent" block; older ones are in extra pages that the client did not read (it logged a warning only) | The client now reads every extra page that overlaps the window and removes duplicates; a company with no 10-K gets a `no_filings` manifest row; three new tests |
| 16 | Review | Docker images used Python 3.12 while the models were trained on 3.14 | Default base image version | All images use Python 3.14, so the pickled model is loaded by the Python version that wrote it |
| 17 | ST-27 | A fresh environment could not be built | Requirements had only minimum versions, and the frozen lock file contained a PyTorch build available only from PyTorch's index; nothing in the project uses PyTorch | Removed PyTorch and its extra index; exact versions pinned in every requirements file and in `requirements.lock` |
| 18 | ST-27 | One test failed only under `mlflow run` | `mlflow run` sets `MLFLOW_RUN_ID`, and the test's `start_run()` tried to resume that run in its own temporary store | An automatic fixture in `tests/conftest.py` removes MLflow run variables for every test |
| 19 | Review | No enforced coding style: 28 flake8 warnings and 59 files not in black format | No style configuration | `.flake8` and black settings added, all warnings fixed, and the DVC `lint` stage fails on any new warning |
| 20 | Review | The model server ran as root, and the Grafana admin password was hard-coded in the compose file | Defaults | Non-root user in the model image; password read from the git-ignored `.env`; static tests for both |
| 21 | Review | Only the backend was monitored; the model server, frontend and other containers had no metrics | MLflow serving and Streamlit have no Prometheus endpoint | cAdvisor added and scraped; container CPU, memory and count panels; `ModelServerContainerDown` and `ScrapeTargetDown` alerts |

## 10. Limitations and Residual Risks

- **No detectable predictive signal.** Acceptance criterion AC-3 is not met, and the application states plainly that the score is of limited reliability. A larger dataset is the main route to a more informative result.
- **Parsing coverage.** 100% applies to the 318 selected filings after excluding five companies. It does not claim the extractor handles every filing layout.
- **Latency measured lightly.** One client, one machine, no concurrency.
- **Retraining window.** Retraining re-fits on the same data window, so without new filings it reproduces the same model. This is shown here as a demonstration of the mechanism.
- **Alerts are not delivered.** Prometheus evaluates and displays them; nothing is sent.
- **No encryption in transit.** All traffic is plain HTTP on one machine. The model file's integrity is checked, but nothing is encrypted.
- **Deployment prerequisite.** The stack needs the output folders from `dvc repro` before it starts, and application code changes need a rebuild, not just a restart.

## 11. Conclusion

The system works end to end and was tested at every level: 126 automated tests pass with no style warnings, all 27 manual system tests pass after fixes, and seven of eight acceptance criteria are met. The one unmet criterion is a statement about the data, not the engineering: with 202 training filings the model is indistinguishable from chance, and this is reported openly, with confidence intervals, a positive-control test, and an application that says so to its users. Testing and review were productive: they found twenty-one real problems, including four that only appeared when the full stack ran and one that silently removed data, and each is now guarded by a test or a documented process step.
