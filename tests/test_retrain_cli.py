from src.drift import retrain


class Dummy:
    def __init__(self, *a, **k):
        pass


def run_main(monkeypatch, argv, params_tolerance=0.01):
    seen = {}

    def fake_orchestrate(runner, registry, tolerance, force, simulate):
        seen.update(tolerance=tolerance, force=force, simulate=simulate)
        return {"retrained": False}

    monkeypatch.setattr(
        retrain,
        "load_params",
        lambda *a, **k: {
            "mlflow": {"tracking_uri": "x", "registered_model_name": "m"},
            "retrain": {"promotion_tolerance": params_tolerance},
        },
    )
    monkeypatch.setattr(retrain, "MlflowRegistry", Dummy)
    monkeypatch.setattr(retrain, "DvcRunner", Dummy)
    monkeypatch.setattr(retrain, "orchestrate", fake_orchestrate)
    monkeypatch.setattr(retrain, "setup_logging", lambda *a, **k: None)
    monkeypatch.setattr("sys.argv", ["retrain"] + argv)
    retrain.main()
    return seen


def test_tolerance_comes_from_params_by_default(monkeypatch):
    assert run_main(monkeypatch, ["--force"], params_tolerance=0.02)["tolerance"] == 0.02


def test_tolerance_flag_overrides_params_including_negative_values(monkeypatch):
    seen = run_main(monkeypatch, ["--force", "--tolerance", "-1"])
    assert seen["tolerance"] == -1.0 and seen["force"] is True
