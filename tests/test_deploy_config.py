"""Static checks that the deployment files agree with each other and with the code.

Docker is not needed: these catch the usual wiring mistakes (wrong host names, a panel
that does not exist, a dashboard querying a metric the backend never exports).
"""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
SERVICES = COMPOSE["services"]
DASH = json.loads((ROOT / "monitoring/grafana/dashboards/filinglens.json").read_text())


def test_expected_services_exist():
    assert {"model-server", "backend", "frontend", "prometheus", "grafana", "mlflow-ui"} <= set(SERVICES)


def test_frontend_and_backend_are_separate_images():
    fe, be = SERVICES["frontend"]["build"], SERVICES["backend"]["build"]
    assert fe["dockerfile"] != be["dockerfile"]
    assert (ROOT / fe["dockerfile"]).exists() and (ROOT / be["dockerfile"]).exists()


def test_loose_coupling_wiring():
    fe_env = SERVICES["frontend"]["environment"]
    be_env = SERVICES["backend"]["environment"]
    assert fe_env["BACKEND_URL"] == "http://backend:8000"  # frontend -> backend only
    assert "MODEL_SERVER_URL" not in fe_env  # frontend never sees the model
    assert be_env["MODEL_SERVER_URL"] == "http://model-server:5001"  # backend -> model via REST
    assert "BACKEND_URL" not in be_env


def test_published_ports_do_not_collide():
    ports = [p.split(":")[0] for s in SERVICES.values() for p in s.get("ports", [])]
    assert len(ports) == len(set(ports))


def test_backend_mounts_are_read_only_and_match_env():
    be = SERVICES["backend"]
    assert all(v.endswith(":ro") for v in be["volumes"])
    env_paths = [be["environment"][k] for k in ("SERVING_DATA_PATH", "MODEL_INFO_PATH", "REPORTS_DIR")]
    mounts = [v.split(":")[1] for v in be["volumes"]]
    for path in env_paths:
        assert any(path == m or path.startswith(m.rstrip("/") + "/") for m in mounts), path


def test_startup_order_waits_for_health():
    assert SERVICES["backend"]["depends_on"]["model-server"]["condition"] == "service_healthy"
    assert SERVICES["frontend"]["depends_on"]["backend"]["condition"] == "service_healthy"


def test_prometheus_scrapes_the_backend():
    cfg = yaml.safe_load((ROOT / "monitoring/prometheus.yml").read_text())
    job = cfg["scrape_configs"][0]
    assert job["metrics_path"] == "/metrics" and job["static_configs"][0]["targets"] == ["backend:8000"]


def test_grafana_provisioning_points_at_prometheus_service():
    ds = yaml.safe_load((ROOT / "monitoring/grafana/provisioning/datasources/datasource.yml").read_text())
    assert ds["datasources"][0]["url"] == "http://prometheus:9090"
    assert ds["datasources"][0]["uid"] == "prometheus"


def test_dashboard_queries_only_exported_metrics():
    source = (ROOT / "api/metrics.py").read_text()
    exprs = " ".join(t["expr"] for p in DASH["panels"] for t in p["targets"])
    used = set(re.findall(r"filinglens_[a-z_]+", exprs))
    assert used
    for name in used:
        base = re.sub(r"_(bucket|sum|count)$", "", name)
        assert f'"{base}"' in source, f"dashboard uses {name} but api/metrics.py never defines {base}"


def test_dashboard_panel_ids_unique_and_embedded_panels_exist():
    from frontend.formatting import CONSOLE_PANELS, GRAFANA_DASHBOARD_UID

    ids = [p["id"] for p in DASH["panels"]]
    assert len(ids) == len(set(ids))
    assert DASH["uid"] == GRAFANA_DASHBOARD_UID
    assert {panel_id for _, panel_id, _ in CONSOLE_PANELS} <= set(ids)


@pytest.mark.parametrize(
    "dockerfile,needle",
    [
        ("docker/Dockerfile.backend", "api.main:create_app"),
        ("docker/Dockerfile.frontend", "frontend/app.py"),
        ("docker/Dockerfile.model", "mlflow"),
    ],
)
def test_dockerfile_entrypoints(dockerfile, needle):
    assert needle in (ROOT / dockerfile).read_text()
    if "/" in needle and needle.endswith(".py"):
        assert (ROOT / needle).exists()


def test_backend_factory_is_importable():
    from api.main import create_app

    assert callable(create_app)


def test_backend_image_has_no_ml_dependencies():
    reqs = (ROOT / "api/requirements.txt").read_text().lower()
    for heavy in ("scikit-learn", "xgboost", "mlflow", "pandas", "numpy", "streamlit"):
        assert heavy not in reqs


def test_api_package_does_not_import_training_code():
    for f in (ROOT / "api").glob("*.py"):
        text = f.read_text()
        assert "from src" not in text and "import src" not in text, f.name


def test_dvc_pipeline_has_serving_stages_in_order():
    stages = yaml.safe_load((ROOT / "dvc.yaml").read_text())["stages"]
    assert list(stages)[-2:] == ["serving_data", "export_model"]
    assert "models/champion" in stages["export_model"]["outs"]
    # the download stage must not depend on the whole ingestion folder (price code lives there too)
    assert "src/ingestion" not in stages["download"]["deps"]
