# Phase 2 runbook: prices, labels, features, models, MLflow

## What is new
| Stage | Module | Output |
|---|---|---|
| `prices` | `src/ingestion/download_prices.py` | `data/prices/prices.csv` (daily adjusted closes + SPY) |
| `labels` | `src/labels/make_labels.py` | `data/labels/labels.csv` (30-trading-day abnormal return, target) |
| `features` | `src/features/build_features.py` | `data/features/features.csv`, `tfidf_vectorizer.joblib` |
| `train` | `src/training/train.py` | MLflow runs + registered model `filinglens-risk` (alias `champion`) |

## Apply
```bash
cd ~/Documents/ml_project
cp filinglens/params.yaml filinglens/params.yaml.bak      # only params.yaml, dvc.yaml,
cp filinglens/dvc.yaml filinglens/dvc.yaml.bak            # requirements.txt are replaced
unzip -o ~/Downloads/filinglens_phase2.zip                # merges into ./filinglens
cd filinglens
pip install -r requirements.txt
printf "mlflow.db\nmlartifacts/\n" >> .gitignore
```

## Loughran-McDonald dictionary (manual, once)
Follow `data/external/README.md`, then:
```bash
dvc add data/external/LM_MasterDictionary.csv
git add data/external/LM_MasterDictionary.csv.dvc data/external/.gitignore data/external/README.md
```

## Run
```bash
pytest                       # 31 tests, all offline
dvc repro                    # download + parse are unchanged, so they are skipped
dvc metrics show             # labels, features and training metrics
mlflow ui --backend-store-uri sqlite:///mlflow.db     # http://127.0.0.1:5000
```
Commit afterwards:
```bash
git add dvc.lock dvc.yaml params.yaml requirements.txt reports src tests data/*/.gitignore README_PHASE2.md .gitignore
git commit -m "Phase 2: prices, labels, features, MLflow training"
git tag phase2 && dvc push
```

## Design choices worth knowing for the viva
- **Label:** base = close on the last trading day on/before the filing date; target = 1 if
  the stock underperforms SPY over the next 30 trading days.
- **No look-ahead:** TF-IDF is fitted only on training-period filings; a 45-day embargo
  separates train from test so no training label window overlaps the test period.
- **Model selection** uses time-ordered cross-validation inside the training period, not the
  test set. Test metrics are reported for all three models afterwards.
- **First filing per company** has no prior year, so it is excluded from modelling but kept
  in `features.csv` (the app can still show it).
- **Reproducibility:** every MLflow run is tagged with the Git commit, a dirty-tree flag, and
  SHA-256 hashes of the feature and label files. `reports/train_run.json` records the
  champion's run ID.
- **Rollback:** move the `champion` alias to an earlier model version in the MLflow registry.

## Phase 2 definition of done
- [ ] `dvc repro` completes through `train`
- [ ] `reports/labels_metrics.json` shows most filings labeled
- [ ] Three runs visible in the MLflow UI, each with params, metrics, artifacts, git tag
- [ ] `filinglens-risk` registered with alias `champion`
- [ ] `reports/model_comparison.csv` saved for the docs
- [ ] HLD draft started (design choices above)

## Known risks
- **Price source:** yfinance is unofficial and can rate-limit or change. If the download fails,
  rerun later; if it keeps failing, only `fetch_prices()` needs swapping for another source.
- **Small data:** expect roughly 150-200 training and 50-70 test filings. Metrics will be noisy
  and near chance; that is normal. Report them honestly next to the baseline.
- **Cloudpickle model format:** chosen because MLflow 3's default (skops) rejects XGBoost's
  numpy types. Safe here because models are produced and loaded locally.
