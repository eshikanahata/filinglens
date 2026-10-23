# FilingLens: Low-Level Design Document

Eshika Nahata (DA24B004) | Individual project | Version 1.1 | API version 1.0.0

## 1. Purpose and Conventions

This document specifies the interfaces and internal rules of FilingLens precisely enough to rebuild or test them: the backend endpoints with their input and output specifications, the interface to the model server, the error model, configuration, data file formats, metrics, business rules, and pipeline stage contracts. The design rationale is in the High-Level Design document. The endpoint tables below were generated from the running application's own schema, so they match the code.

**Conventions**

- All API bodies are JSON, UTF-8. Interactive API documentation is served by the backend at `/docs`.
- Base URL: `http://localhost:8000` from the host, `http://backend:8000` inside the Docker network.
- Dates are ISO 8601 (`YYYY-MM-DD`). Timestamps are UTC (`YYYY-MM-DDTHH:MM:SS+00:00`).
- Ratios and changes are decimal fractions: `0.18` means 18%. Changes in word shares are fractions of all words: `0.001` means 0.1 percentage points.
- Ticker symbols are case-insensitive and must match `^[A-Za-z][A-Za-z.\-]{0,9}$`.
- Optional fields are present with value `null` when not available; they are never omitted.
- All endpoints use HTTP GET and have no side effects other than metrics counters.

## 2. Backend Module Design

| Module | Responsibility |
| --- | --- |
| `api/main.py` | Application factory `create_app(settings, model_client)`; routes; request instrumentation middleware; error handlers. Started with `uvicorn api.main:create_app --factory`. |
| `api/config.py` | `Settings` dataclass read from environment variables; the disclaimer text. |
| `api/schemas.py` | Pydantic response models (the contract in section 3). |
| `api/data_store.py` | Loads the serving data file once at startup; lookups by ticker and accession. Fails fast with a clear message if the file is missing. |
| `api/model_client.py` | The only code that talks to the model server (`/ping`, `/invocations`). |
| `api/explain.py` | Signal labels and the plain-English "what stands out" statements. |
| `api/pipeline_status.py` | Reads stage reports, the model comparison, the Ray benchmark, the drift report and the event log. |
| `api/metrics.py` | Prometheus metric definitions and the custom collector for pipeline metrics. |

The backend imports no training code and no machine-learning libraries. The factory takes the model client as an optional argument, so tests inject a fake model server.

## 3. Endpoint Definitions

### 3.1 `GET /health`

Liveness and dependency check. Always returns 200 so the container is considered alive; the `status` field reports whether the model server is reachable (it calls the model server's `/ping`).

**Parameters:** none.

**Response 200** (`HealthResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `status` | string | `ok` if the model server answers, otherwise `degraded` |
| `model_server` | string | `up` or `down` |
| `filings_loaded` | integer | Number of filings in the serving data |
| `companies` | integer | Number of distinct companies |

```json
{"status": "ok", "model_server": "up", "filings_loaded": 318, "companies": 54}
```

### 3.2 `GET /tickers`

The companies that can be analysed, sorted alphabetically.

**Parameters:** none.

**Response 200** (`TickersResponse`): `tickers`: array of `TickerItem`

| Field | Type | Description |
| --- | --- | --- |
| `ticker` | string | Upper-case symbol |
| `n_filings` | integer | Filings available for the company |
| `latest_filing_date` | string | Date of the company's most recent filing |

```json
{"tickers": [{"ticker": "AAPL", "n_filings": 5, "latest_filing_date": "2025-10-31"}]}
```

### 3.3 `GET /analysis/{ticker}`

Analysis of a company's most recent filing.

**Path parameter:** `ticker` (string, pattern above, case-insensitive).

**Behaviour**

1. Reject an invalid pattern with 400 and an unknown company with 404.
2. Take the filing with the latest filing date and its prior-year filing, if any.
3. If a prior-year filing exists, call the model server once to score the filing; otherwise the filing is not scored.
4. Derive the signal label from the score (section 9.1) and the explanation statements (section 9.2).

**Response 200** (`AnalysisResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `ticker` | string | Upper-case symbol |
| `filing` | `FilingRef` | The analysed filing |
| `previous_filing` | `FilingRef` or null | The prior-year filing used for comparison |
| `signal` | `Signal` | Risk signal |
| `reasons` | array of string | One to four "what stands out" statements |
| `changes` | `Changes` | Year-over-year changes |
| `model` | `ModelInfo` or null | The model that produced the score |
| `disclaimer` | string | Fixed decision-support disclaimer |

`FilingRef`

| Field | Type | Description |
| --- | --- | --- |
| `accession` | string | SEC accession number |
| `filing_date` | string | Date filed |
| `report_date` | string or null | Fiscal period end date |

`Signal`

| Field | Type | Description |
| --- | --- | --- |
| `label` | string | `Elevated`, `Moderate`, `Lower`, or `Not enough data` |
| `score` | number or null | Estimated probability (0 to 1) of underperforming the market benchmark over the 30 trading days after filing; null if not scored |
| `elevated_threshold` | number | Score at or above which the label is `Elevated` (default 0.60) |
| `low_threshold` | number | Score at or below which the label is `Lower` (default 0.40) |

`Changes`

| Field | Type | Description |
| --- | --- | --- |
| `risk_section_change_pct` | number or null | Change in the risk section's word count versus last year (0.18 = +18%) |
| `text_similarity` | number or null | TF-IDF cosine similarity with last year's risk section, 0 to 1 |
| `negative_tone_change` | number or null | Change in the share of negative words |
| `uncertainty_change` | number or null | Change in the share of uncertainty words |
| `litigious_change` | number or null | Change in the share of litigation-related words |
| `readability_grade_change` | number or null | Change in Flesch-Kincaid grade level |
| `new_terms` | array of string | Terms given more emphasis than last year (up to 8) |
| `dropped_terms` | array of string | Terms given less emphasis (up to 8) |

`ModelInfo`

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | Model type, for example `xgboost` |
| `version` | string | Registry version |
| `run_id` | string | MLflow run that trained it |
| `test_roc_auc` | number or null | Held-out test ROC-AUC |
| `cv_roc_auc` | number or null | Cross-validation ROC-AUC |

**Example** (scored)

```json
{
  "ticker": "AAPL",
  "filing": {"accession": "0000320193-25-000079", "filing_date": "2025-10-31", "report_date": "2025-09-27"},
  "previous_filing": {"accession": "0000320193-24-000123", "filing_date": "2024-11-01", "report_date": "2024-09-28"},
  "signal": {"label": "Moderate", "score": 0.52, "elevated_threshold": 0.6, "low_threshold": 0.4},
  "reasons": [
    "The risk-factors section grew 18% compared with last year (higher than 90% of filings in this dataset).",
    "The risk-factors wording is 74% similar to last year (lower than 90% of filings in this dataset)."
  ],
  "changes": {"risk_section_change_pct": 0.18, "text_similarity": 0.74, "negative_tone_change": 0.0004,
              "uncertainty_change": 0.0011, "litigious_change": 0.0, "readability_grade_change": 0.3,
              "new_terms": ["supply chain"], "dropped_terms": ["covid"]},
  "model": {"name": "logistic_regression", "version": "3", "run_id": "5dd9fce2", "test_roc_auc": 0.444, "cv_roc_auc": 0.4829},
  "disclaimer": "FilingLens is decision support, not financial advice. ..."
}
```

**Example** (company's earliest filing): `previous_filing` is `null`; `signal` is `{"label": "Not enough data", "score": null, ...}`; `reasons` is the single statement "This is the earliest filing we have for this company, so there is no prior year to compare against."; the model server is not called.

**Errors:** 400 `invalid_input`, 404 `unknown_ticker`, 503 `model_unavailable` (section 4).

### 3.4 `GET /analysis/{ticker}/history`

The signal across all of a company's filings, oldest first.

**Path parameter:** `ticker`, as above.

**Behaviour:** filings that have a prior-year filing are scored together in a single model-server call; the first filing of a company has no prior year and is not scored.

**Response 200** (`HistoryResponse`): `ticker` (string) and `points`: array of `HistoryPoint`

| Field | Type | Description |
| --- | --- | --- |
| `accession` | string | SEC accession number |
| `filing_date` | string | Date filed |
| `score` | number or null | Score, null if not scored |
| `label` | string | Signal label |
| `text_similarity` | number or null | Similarity with the prior year, null if none |

```json
{"ticker": "AAPL", "points": [
  {"accession": "...", "filing_date": "2023-11-03", "score": null, "label": "Not enough data", "text_similarity": null},
  {"accession": "...", "filing_date": "2024-11-01", "score": 0.48, "label": "Moderate", "text_similarity": 0.81},
  {"accession": "...", "filing_date": "2025-10-31", "score": 0.52, "label": "Moderate", "text_similarity": 0.74}
]}
```

**Errors:** 400, 404, 503, as for 3.3.

### 3.5 `GET /pipeline/runs`

Status of the data and model pipeline, for the console page.

**Parameters:** none.

**Response 200** (`PipelineResponse`)

| Field | Type | Description |
| --- | --- | --- |
| `stages` | array of `StageStatus` | One entry per stage, in the order below |
| `model_comparison` | array of object | One row per trained model, from `reports/model_comparison.csv`. Values are strings, as read from the CSV. |
| `test_uncertainty` | array of object | Bootstrap confidence intervals per model, from `reports/test_uncertainty.csv` (strings) |
| `ray_benchmark` | array of object | Throughput by worker count: `workers`, `filings_per_minute`, `speedup_vs_1_worker`, and others |
| `parse_failure_count` | integer | Rows in `reports/parse_failures.csv` |
| `drift_report` | object or null | Contents of `reports/drift_report.json` (section 7.4) |
| `events` | array of object | The 20 most recent pipeline events, newest first (section 7.5) |
| `champion` | `ModelInfo` or null | The currently served model |

`StageStatus`

| Field | Type | Description |
| --- | --- | --- |
| `name` | string | `download`, `parse`, `prices`, `labels`, `features`, `train`, or `drift` |
| `status` | string | `ok`, `warning`, or `missing` |
| `updated_at` | string or null | File modification time of the stage's metrics report |
| `metrics` | object | Contents of the stage's metrics report (empty if missing) |

**Status rules:** `missing` if the stage's report file is absent or unreadable. `warning` if: download has any failed filing; parse success rate is below 0.95; prices has any missing or sparse symbol; drift reports `drift_detected` = 1. Otherwise `ok`.

### 3.6 `GET /metrics`

Prometheus text exposition format (not JSON). Excluded from the generated OpenAPI document. Metric names and meanings are listed in section 8.

## 4. Error Model

Every error response has the same shape and never contains a stack trace or an internal address:

```json
{"error": {"code": "unknown_ticker", "message": "We don't have data for 'ZZZ'. Pick a company from the supported list."}}
```

| HTTP | `code` | When | Message shown to the user |
| --- | --- | --- | --- |
| 400 | `invalid_input` | The ticker does not match the allowed pattern. Framework validation errors are mapped to this code, so the API never returns 422. | Please enter a valid ticker symbol: letters only, for example AAPL. |
| 404 | `unknown_ticker` | A valid ticker that is not in the dataset | We don't have data for 'XYZ'. Pick a company from the supported list. |
| 503 | `model_unavailable` | The model server is unreachable, times out, returns an error, or returns an unusable reply | The scoring service is temporarily unavailable. Please try again shortly. |
| 500 | `internal_error` | Any unexpected exception (logged on the server with its stack trace) | Something went wrong on our side. Please try again. |

## 5. Interface to the Model Server

The backend knows the model server only through `MODEL_SERVER_URL` and this contract.

**Health:** `GET {MODEL_SERVER_URL}/ping` returns 200 when the model is loaded.

**Scoring:** `POST {MODEL_SERVER_URL}/invocations`, content type JSON.

Request:

```json
{"dataframe_split": {"columns": ["neg_ratio", "pos_ratio", "..."], "data": [[0.0123, 0.0041, 0.0]]}}
```

- `columns` is the feature list taken from the serving data file, in the order the model was trained with: `neg_ratio, unc_ratio, lit_ratio, pos_ratio, fk_grade, avg_sentence_len, log_risk_words, risk_share, risk_words_change, tfidf_similarity, d_neg_ratio, d_unc_ratio, d_lit_ratio, d_fk_grade`.
- `data` has one row per filing. A missing value is sent as `null`.

Response: `{"predictions": [[0.48, 0.52]]}`: one pair per row, `[P(not underperform), P(underperform)]`. The backend uses the second element.

**Validation and failure handling** (all map to HTTP 503 `model_unavailable` and increment the failed-call counter):

- network error or timeout (default 5 seconds);
- non-2xx status or unparseable body;
- predictions that are not pairs (for example plain class labels);
- a number of predictions different from the number of rows sent.

## 6. Configuration

All configuration is read from environment variables at startup, so the same container images run in any environment. Defaults are shown.

**Backend**

| Variable | Default | Meaning |
| --- | --- | --- |
| `MODEL_SERVER_URL` | `http://model-server:5001` | Address of the model server |
| `MODEL_TIMEOUT_SECONDS` | `5.0` | Timeout for model-server calls |
| `SERVING_DATA_PATH` | `data/serving/filings.json` | Precomputed per-filing data |
| `MODEL_INFO_PATH` | `models/champion_info.json` | Description of the served model |
| `REPORTS_DIR` | `reports` | Stage reports, drift report, event log |
| `ELEVATED_THRESHOLD` | `0.60` | Score at or above which the label is Elevated |
| `LOW_THRESHOLD` | `0.40` | Score at or below which the label is Lower |

**Frontend**

| Variable | Default | Meaning |
| --- | --- | --- |
| `BACKEND_URL` | `http://localhost:8000` | Address of the backend (the only service the frontend calls) |
| `GRAFANA_URL` | `http://localhost:3000` | Opened by the user's browser for embedded panels |
| `MLFLOW_UI_URL` | `http://localhost:5000` | Link shown on the console page |
| `PROMETHEUS_URL` | `http://localhost:9090` | Link shown on the console page |

**Pipeline:** `EDGAR_USER_AGENT` (a real name and contact address, required by SEC; read from the environment or a `.env` file that is never committed). All other pipeline settings are in `params.yaml`, which DVC tracks, so changing a value reruns exactly the stages that depend on it.

## 7. Data File Specifications

### 7.1 Serving data: `data/serving/filings.json`

Produced by the `serving_data` stage and read by the backend.

| Field | Type | Description |
| --- | --- | --- |
| `version` | integer | Format version (currently 1) |
| `feature_columns` | array of string | Model input columns, in training order (section 5) |
| `filings` | array of object | One entry per filing |

Each filing entry:

| Field | Type | Description |
| --- | --- | --- |
| `ticker`, `accession`, `filing_date`, `report_date` | string | Identification and dates |
| `has_prior` | boolean | True if a filing 300 to 450 days earlier exists |
| `prior_accession` | string or null | That earlier filing |
| `features` | object | One number (or null) for each column in `feature_columns` |
| `percentiles` | object | Percentile rank (0 to 100) for six change features: `risk_words_change`, `tfidf_similarity`, `d_neg_ratio`, `d_unc_ratio`, `d_lit_ratio`, `d_fk_grade`. Empty when there is no prior year. |
| `new_terms`, `dropped_terms` | array of string | Terms whose weight rose or fell most versus the prior year |

### 7.2 Served model description: `models/champion_info.json`

| Field | Description |
| --- | --- |
| `registered_model` | Registry name (`filinglens-risk`) |
| `alias` | `champion` |
| `version` | Registry version being served |
| `champion_model` | Model type (`xgboost` or `logistic_regression`) |
| `run_id` | MLflow run that trained it |
| `git_commit` | Commit hash at training time |
| `test_roc_auc`, `cv_roc_auc` | Held-out and cross-validation scores |
| `model_sha256` | SHA-256 of `model.pkl`, also written to `models/champion/model.sha256` in `sha256sum` format. The model-server container runs `sha256sum -c model.sha256` before serving and refuses to start on a mismatch |

### 7.3 Stage reports (in `reports/`)

| File | Written by | Fields |
| --- | --- | --- |
| `download_metrics.json` | download | `tickers`, `filings_total`, `filings_ok`, `filings_failed`, `elapsed_seconds` |
| `parse_metrics.json` | parse | `workers`, `filings_total`, `filings_ok`, `filings_failed`, `success_rate`, `elapsed_seconds`, `filings_per_minute` |
| `parse_failures.csv` | parse | `ticker`, `accession`, `error` (one row per failed filing) |
| `prices_metrics.json` | prices | `symbols_requested`, `symbols_ok`, `symbols_missing`, `symbols_sparse`, `trading_days`, `first_date`, `last_date` |
| `labels_metrics.json` | labels | `filings_total`, `filings_labeled`, `filings_unlabeled`, `positive_rate`, `horizon_trading_days` |
| `features_metrics.json` | features | `filings`, `with_prior`, `tfidf_fit_filings`, `tfidf_vocab`, `train_end` |
| `train_metrics.json` | train | `champion_cv_roc_auc`, `champion_test_roc_auc`, `champion_test_accuracy`, `baseline_test_accuracy`, `beats_baseline_accuracy`, `n_train`, `n_test` |
| `train_run.json` | train | `champion_model`, `champion_run_id`, `registered_model`, `registered_version`, `git_commit`, `git_dirty`, `features_sha256`, `labels_sha256` |
| `model_comparison.csv` | train | `model`, `run_id`, `model_uri`, `cv_roc_auc`, and `test_` accuracy, balanced accuracy, ROC-AUC, precision, recall, F1 |
| `test_uncertainty.csv` | evaluate\_uncertainty | per model: `n`, `auc`, `auc_ci_low`, `auc_ci_high`, `accuracy`, `acc_ci_low`, `acc_ci_high`, `auc_ci_includes_0.5` |
| `ray_benchmark.json` | benchmark\_ray | array: `workers`, `filings_total`, `success_rate`, `elapsed_seconds`, `filings_per_minute`, `speedup_vs_1_worker` |
| `drift_metrics.json` | drift | `drift_detected` (0 or 1), `drifted_features`, `drifted_share`, `max_psi`, `n_reference`, `n_current`, `simulated` (0 or 1) |

### 7.4 Drift report: `reports/drift_report.json`

| Field | Description |
| --- | --- |
| `status` | `ok`, or `insufficient_data` when there are too few recent filings to test |
| `simulated` | True if the current batch was deliberately shifted (demonstration) |
| `drift_detected` | Batch-level decision |
| `n_features`, `n_drifted`, `drifted_share`, `max_psi` | Summary |
| `n_reference`, `n_current` | Filings in the training period and in the current batch |
| `features` | Object keyed by feature name: `psi`, `ks_stat`, `ks_pvalue`, `drifted` |
| `thresholds` | `psi`, `ks_alpha`, `min_drifted_share` in force for this report |

### 7.5 Event log: `reports/run_history.jsonl`

One JSON object per line, appended and never rewritten. Common fields: `ts` (UTC timestamp), `event`, `status` (`ok` or `warning`, or `drift` for a drift check that found drift).

| `event` | Extra fields | Written when |
| --- | --- | --- |
| `drift_check` | `drifted_features`, `max_psi`, `simulated`, `n_current` | The drift stage runs |
| `retrain_started` | `reason` (`drift` or `forced`), `previous_version` | The orchestrator begins retraining |
| `model_promoted` | `version`, `previous_version`, `prev_cv_auc`, `new_cv_auc` | The new model is kept |
| `model_rollback` | `rejected_version`, `restored_version`, `prev_cv_auc`, `new_cv_auc` | The new model was worse and the previous one was restored (status `warning`) |
| `model_exported` | `version` | The serving folder was refreshed |

## 8. Prometheus Metrics and Alert Rules

The backend exposes these at `/metrics`. Request and model metrics are updated as requests happen; pipeline and drift metrics are read from the reports at scrape time.

| Metric | Type | Labels | Meaning |
| --- | --- | --- | --- |
| `filinglens_http_requests_total` | counter | method, endpoint, status | Requests served (endpoint is the route template, not the raw path) |
| `filinglens_http_request_duration_seconds` | histogram | endpoint | Request latency |
| `filinglens_model_requests_total` | counter | outcome | Model-server calls, `success` or `error` |
| `filinglens_model_latency_seconds` | histogram | none | Model-server call latency |
| `filinglens_risk_score` | histogram | none | Distribution of returned scores (buckets 0.1 to 1.0) |
| `filinglens_analysis_total` | counter | signal | Analyses served by signal label |
| `filinglens_pipeline_filings` | gauge | stage, outcome | Filings ok and failed in download and parse |
| `filinglens_parse_success_ratio` | gauge | none | Share of filings parsed |
| `filinglens_parse_filings_per_minute` | gauge | none | Parsing throughput |
| `filinglens_parse_workers` | gauge | none | Ray workers in the last parse |
| `filinglens_labels_positive_rate` | gauge | none | Share of labelled filings that underperformed |
| `filinglens_labels_unlabeled` | gauge | none | Filings without a label yet |
| `filinglens_train_champion_test_roc_auc`, `filinglens_train_champion_cv_roc_auc` | gauge | none | Champion scores |
| `filinglens_train_samples` | gauge | none | Training filings |
| `filinglens_ray_speedup` | gauge | workers | Parsing speed-up versus one worker |
| `filinglens_model_info` | gauge | model, version | Served model (value always 1) |
| `filinglens_drift_detected` | gauge | none | 1 if the latest batch drifted |
| `filinglens_drift_features_drifted`, `filinglens_drift_max_psi` | gauge | none | Drift summary |
| `filinglens_drift_simulated` | gauge | none | 1 if the report used a deliberately shifted batch |
| `filinglens_drift_psi` | gauge | feature | PSI per feature |
| `filinglens_pipeline_events` | gauge | event | Count of logged events by type |

**Alert rules** (`monitoring/alerts.yml`, shown in Prometheus; no notifications are sent)

| Alert | Condition | For | Severity |
| --- | --- | --- | --- |
| `BackendDown` | the backend scrape target is down | 1 min | critical |
| `ModelServerErrors` | any failed model-server calls in the last 5 minutes | 1 min | critical |
| `HighServerErrorRate` | more than 5% of requests return 5xx | 2 min | warning |
| `SlowResponses` | 95th percentile latency above 1 second | 5 min | warning |
| `ParseSuccessBelowTarget` | parse success ratio below 0.95 | 1 min | warning |
| `DataDriftDetected` | drift flag equals 1 | 1 min | warning |
| `ModelServerContainerDown` | cAdvisor no longer reports a running model-server container | 1 min | critical |
| `ScrapeTargetDown` | any scrape target other than the backend is down (cAdvisor, Prometheus) | 1 min | warning |

**Container metrics** come from cAdvisor (job `cadvisor`, `cadvisor:8080`), not from the backend. The dashboard uses `container_cpu_usage_seconds_total` (CPU per container), `container_memory_working_set_bytes` (memory per container) and `container_last_seen` (containers running), filtered to named containers. Prometheus also scrapes itself (job `prometheus`).

## 9. Business Rules

### 9.1 Signal label

The score is the model's estimated probability that the stock underperforms the SPY benchmark over the 30 trading days after the filing date. The label is `Not enough data` if the filing was not scored; `Elevated` if score is at or above the elevated threshold; `Lower` if at or below the low threshold; otherwise `Moderate`. A filing is scorable only if it has a prior-year filing, meaning one filed between 300 and 450 days earlier.

### 9.2 "What stands out" statements

For a scored filing the backend considers six candidate statements, each describing one change compared with last year:

| Feature | Statement pattern |
| --- | --- |
| `risk_words_change` | The risk-factors section grew (or shrank) X% compared with last year |
| `tfidf_similarity` | The risk-factors wording is X% similar to last year |
| `d_neg_ratio` | The share of negative-tone words rose (or fell) by X percentage points |
| `d_unc_ratio` | The share of uncertainty words rose (or fell) by X percentage points |
| `d_lit_ratio` | The share of litigation-related words rose (or fell) by X percentage points |
| `d_fk_grade` | The risk section became harder (or easier) to read (X grade levels) |

A statement is included only if the filing's percentile for that feature is 80 or above, or 20 or below. Each is followed by a phrase such as `(higher than 90% of filings in this dataset)`, using the percentile or 100 minus it. Statements are ordered by distance of the percentile from 50, most unusual first, and at most four are returned. If none qualifies, a single statement says nothing stands out. The statements are descriptive comparisons with other filings. They do not explain the model's score.

### 9.3 Percentiles and changed terms

A percentile is the rank (0 to 100) of a filing's value among all filings that have a prior year, across training and test periods. It is descriptive only and never used for modelling. `new_terms` and `dropped_terms` list up to eight terms whose TF-IDF weight rose (or fell) most between the filing and its prior-year filing, counting only strict increases (or decreases).

## 10. Pipeline Stage Contracts

| Stage | Command (module) | Inputs | Parameter groups | Outputs | Metrics file |
| --- | --- | --- | --- | --- | --- |
| lint | `flake8 api frontend src tests scripts` | code, `.flake8` | none | `reports/lint_report.txt` (empty plus a pass line when clean; the stage fails on any warning) | none |
| test | `pytest -q --junitxml=...` then `scripts/summarize_tests.py` | code, tests, `pytest.ini`, lint report | none | `pytest_results.xml`, `test_summary.md` | `test_summary.json` |
| download | `src.ingestion.download_filings` | ticker list, SEC EDGAR (submissions `recent` block plus older pages) | data, edgar | `data/raw` (filing HTML, `manifest.csv` with one row per filing and a `no_filings` row for a ticker without 10-Ks in the window) | `download_metrics.json` (includes `tickers_without_filings`) |
| parse | `src.parsing.parse_filings` | `data/raw` | parsing | `data/parsed` (one JSON per filing: ticker, accession, dates, `risk_factors`, `risk_words`, `full_words`) | `parse_metrics.json` |
| prices | `src.ingestion.download_prices` | ticker list, price source | prices | `data/prices/prices.csv` | `prices_metrics.json` |
| labels | `src.labels.make_labels` | `data/parsed`, `data/prices` | labels | `data/labels/labels.csv` | `labels_metrics.json` |
| features | `src.features.build_features` | `data/parsed`, Loughran-McDonald dictionary | features, split | `data/features` (`features.csv`, `tfidf_vectorizer.joblib`) | `features_metrics.json` |
| train | `src.training.train` | `data/features`, `data/labels` | train, split, labels, mlflow | MLflow runs and registered model; `train_run.json`, `model_comparison.csv` | `train_metrics.json` |
| drift | `src.drift.check_drift` | `data/features` | drift, split | `drift_report.json` | `drift_metrics.json` |
| serving\_data | `src.serving.build_serving_data` | `data/features`, `data/parsed` | features | `data/serving/filings.json` | none |
| export\_model | `src.serving.export_model` | registry, `train_run.json`, `train_metrics.json`, `test_summary.json` (CI gate) | mlflow | `models/champion` (including `model.sha256`), `models/champion_info.json` | none |

Run outside the DVC graph: `src.parsing.benchmark_ray` (writes `ray_benchmark.json`), `src.training.evaluate_uncertainty` (writes `test_uncertainty.csv`), and `src.drift.retrain` (section 11.5).

## 11. Algorithms

### 11.1 Label

Let `d0` be the last trading day on or before the filing date, and `d30` the trading day 30 trading days after `d0`. Stock return = close(d30) / close(d0) - 1; benchmark return likewise for SPY. Abnormal return = stock return minus benchmark return. Target = 1 if abnormal return is below 0. A filing is unlabeled if the price history has fewer than 30 trading days after `d0`, no price on or before the filing date, or a gap of more than 7 days between the filing date and `d0`.

### 11.2 Features

| Feature | Definition |
| --- | --- |
| `neg_ratio`, `pos_ratio`, `unc_ratio`, `lit_ratio` | Share of the risk section's words that appear in the matching Loughran-McDonald category |
| `fk_grade` | 0.39 x words / sentences + 11.8 x syllables / words - 15.59 |
| `avg_sentence_len` | words / sentences |
| `log_risk_words` | natural log of (1 + risk-section word count) |
| `risk_share` | risk-section words / words in the whole filing |
| `risk_words_change` | (words this year - words last year) / words last year |
| `tfidf_similarity` | cosine similarity of the two sections' TF-IDF vectors (English stop words removed, sublinear term frequency, one- and two-word terms, at most 5000 terms, term must appear in at least 3 documents). The vocabulary and weights are fitted on training-period filings only. |
| `d_neg_ratio`, `d_unc_ratio`, `d_lit_ratio`, `d_fk_grade` | Value this year minus value last year |

### 11.3 Split and model selection

Test set: filings dated 2025-07-01 or later. Training set: filings dated up to 45 days before that. Filings in between are dropped. Only filings with a prior year and a label are used. Candidate models are scored by 3-fold expanding-window cross-validation (ROC-AUC) on the training set in date order; the best non-baseline model becomes the champion and is registered with the alias `champion`. Test metrics are logged for every model but are never used to choose between them.

### 11.4 Drift detection

Reference = training-period filings that have a prior year. Current = filings from the drift start date (default: the test start) onward that have a prior year. No labels are needed.

PSI for one feature: split the reference values into 10 bins at their deciles; let `r_i` and `c_i` be the share of reference and current values in bin `i`, each floored at 0.0001; PSI = sum over bins of (c\_i - r\_i) x ln(c\_i / r\_i). A reference with fewer than three distinct bin edges gets PSI 0 if the current values equal it and 1 otherwise. Rule of thumb: below 0.1 stable, 0.2 or more a significant shift.

A feature is drifted if PSI is at least 0.2 AND the two-sample Kolmogorov-Smirnov test gives p below 0.01. The batch has drifted if at least 25% of the 14 features have drifted. If the reference has fewer than 30 filings or the current batch fewer than 20, the report status is `insufficient_data` and no drift is declared.

### 11.5 Drift-triggered retraining

1. Run the drift check (through DVC, or on a deliberately shifted batch with `--simulate-shift`).
2. If drift is detected, or `--force` was given, record the current champion version and its cross-validation AUC, and log `retrain_started`.
3. Rerun the train stage only. Training registers a new version and moves the `champion` alias to it.
4. Promotion rule: keep the new model if its cross-validation AUC plus the tolerance (default 0.01) is at least the previous champion's; otherwise move the alias back to the previous version and log `model_rollback`. A missing or NaN new score always rolls back; no previous champion means the new model is kept.
5. Rerun the export stage so the serving folder matches the champion, and log `model_exported`.
6. The operator recreates the model-server and backend containers to load the new files.

### 11.6 Test-set uncertainty

AUC and accuracy for each model are resampled 2000 times with replacement (fixed seed); the 2.5th and 97.5th percentiles give the 95% interval. The resampling treats filings as independent, so intervals are, if anything, too narrow.

## 12. Frontend Design

The frontend is one Streamlit application. It makes only HTTP GET calls to the backend through `frontend/api_client.py`.

| Page | Content | Backend calls |
| --- | --- | --- |
| Company analysis | Searchable company list; risk signal, score bar, filing date; what stands out; what changed since last year; topics given more or less emphasis; signal history chart and table; model line; disclaimer | `/tickers` (cached for 60 seconds), `/analysis/{ticker}`, `/analysis/{ticker}/history` |
| Pipeline console | Parse success rate, throughput, failed filings, serving model; stage table; Ray speed-up chart; model comparison and confidence intervals; drift summary and table; recent events; four embedded Grafana panels (request rate, 95th percentile latency, parse success ratio, filings by stage outcome); links to Grafana, MLflow and Prometheus | `/pipeline/runs` |
| How to use | Plain-language help and limits | none |

**Error mapping.** The client converts every failure into one exception carrying a message safe to show:

| Situation | Message shown |
| --- | --- |
| Backend unreachable or timeout (10 seconds) | We can't reach the analysis service right now. Please try again in a moment. |
| Backend returns an error body | The backend's own message (section 4) |
| Error status without a readable body | The service returned an unexpected response. Please try again. |
| Success status with an unreadable body | The service returned an unreadable response. Please try again. |

The page shows the message in an error box and stops rendering that section; it never shows a stack trace, a URL, or a host name. Navigation lives in the sidebar, and every analysis page ends with the decision-support disclaimer returned by the backend.
