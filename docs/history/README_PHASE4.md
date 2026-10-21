# Phase 4 (technical part): drift, retraining, rollback, alerting

## What is new
| Piece | Where | Role |
|---|---|---|
| Drift detection | `src/drift/drift.py`, `check_drift.py` | PSI + KS test per feature, label-free, writes `reports/drift_report.json` |
| `drift` DVC stage | `dvc.yaml`, `params.yaml` (`drift:`) | runs after `features`; does NOT trigger training by itself |
| Retrain orchestrator | `src/drift/retrain.py` | drift -> retrain -> promotion gate -> rollback if worse -> re-export |
| Event log | `src/common/run_log.py`, `reports/run_history.jsonl` | history of drift checks, retrains, promotions, rollbacks |
| Alert rules | `monitoring/alerts.yml` | 6 rules, visible at http://localhost:9090/alerts |
| Dashboard + console | `monitoring/grafana/...`, `frontend/app.py` | drift PSI per feature, drift flag, event counts, recent events table |

## Apply
```bash
cd ~/Documents/ml_project/filinglens
cp params.yaml params.yaml.bak && cp dvc.yaml dvc.yaml.bak && cp docker-compose.yml docker-compose.yml.bak
unzip -o ~/Downloads/filinglens_phase4.zip -d /tmp/p4
cp -r /tmp/p4/filinglens/. . && rm -rf /tmp/p4
pytest -q                                   # all green (my run: 105 tests; yours has one extra .env test)
dvc repro                                   # runs the new `drift` stage (and anything stale)
cat reports/drift_metrics.json              # send me this
docker compose up -d --force-recreate prometheus grafana backend frontend
```
`prometheus` must be recreated so it loads `alerts.yml`; `backend` and `frontend` pick up the new code.

## Demo script (also your acceptance evidence)
1. **Real data, no drift expected:** `dvc repro drift`, then `cat reports/drift_metrics.json`.
2. **Deliberate shift, detection and retraining:**
   ```bash
   python -m src.drift.retrain --simulate-shift
   docker compose up -d --force-recreate model-server backend
   ```
   Expect: drift detected, `dvc repro -f -s train` runs (~1-2 min), a new model version is registered,
   the decision is printed, the model is re-exported. Without new data the retrained model is identical
   to the old one, so it is promoted (new CV AUC is within tolerance). That is correct behaviour.
3. **Watch it:** console page (drift table, events), Grafana (drift panels), Prometheus `/alerts`
   (`DataDriftDetected` turns pending, then firing after about a minute).
4. **Show a rollback:** temporarily set `retrain: promotion_tolerance: -1.0` in `params.yaml` (demo only:
   it makes every new model look worse), rerun step 2, and the events table shows `model_rollback`
   with the previous version restored. Put the tolerance back to `0.01` afterwards.
5. **Reset:** `dvc repro drift` restores the real (non-simulated) drift report.

## Design choices worth knowing for the viva
- **Why PSI and KS together:** PSI is noisy on small batches, KS flags harmless shifts; requiring both
  keeps false alarms low. A batch drifts when at least 25% of features have drifted.
- **Why label-free:** new filings have no label for ~6 weeks; drift must be visible immediately.
- **Why retraining is a script around DVC, not a DVC stage:** DVC stages are unconditional; "retrain only
  if drift" needs a decision. The orchestrator makes the decision and then calls the DVC stages.
- **Promotion gate and rollback:** training always registers a new version and moves the `champion` alias.
  The orchestrator compares CV AUC (never test AUC) with the previous champion and moves the alias back
  if the new model is worse by more than the tolerance. The previous version is never deleted.
- **Honest limitation:** retraining re-fits on the same split window. In real use, new filings would be
  ingested (`dvc repro`) and `split.test_start_date` advanced before retraining; the mechanics are the same.
- **Alerts:** rules are evaluated and shown in Prometheus; no notification channel (Alertmanager) is
  configured, because this is a local demo.

## Definition of done (technical part)
- [ ] `dvc repro` completes including `drift`; `reports/drift_metrics.json` exists
- [ ] Simulated shift is detected and triggers retraining (demo step 2)
- [ ] Rollback demonstrated once (demo step 4)
- [ ] `DataDriftDetected` visible in Prometheus; console and Grafana show drift
- [ ] `reports/run_history.jsonl` committed

## Still to do in Phase 4 (documents and viva)
Architecture diagram update (add the drift/retrain loop), HLD, LLD, test plan and test report, user
manual, viva preparation.
