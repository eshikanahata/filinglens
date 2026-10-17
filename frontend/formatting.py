"""Pure display helpers (unit-tested; no Streamlit calls)."""
from typing import Optional

SIGNAL_COLORS = {"Elevated": "red", "Moderate": "orange", "Lower": "green", "Not enough data": "gray"}
STATUS_ICONS = {"ok": "✅ OK", "warning": "⚠️ Needs attention", "missing": "⛔ Not run yet"}
GRAFANA_DASHBOARD_UID = "filinglens-main"
# Grafana panels embedded in the console page: (grid column, panel id, title)
CONSOLE_PANELS = [(0, 1, "Request rate"), (1, 2, "95th percentile latency"),
                  (0, 6, "Parse success ratio"), (1, 8, "Filings by stage outcome")]


def signal_markdown(label: str) -> str:
    return f":{SIGNAL_COLORS.get(label, 'gray')}[**{label}**]"


def fmt_pct(x: Optional[float], digits: int = 0, signed: bool = False) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.{digits}f}%" if signed else f"{x * 100:.{digits}f}%"


def fmt_points(x: Optional[float]) -> str:
    """A change in a word share, shown in percentage points."""
    return "n/a" if x is None else f"{x * 100:+.2f} pts"


def fmt_grade(x: Optional[float]) -> str:
    return "n/a" if x is None else f"{x:+.1f} grades"


def similarity_caption(sim: Optional[float]) -> str:
    if sim is None:
        return ""
    if sim >= 0.9:
        return "Wording is largely unchanged."
    if sim >= 0.75:
        return "Wording changed moderately."
    return "Wording changed substantially."


def grafana_panel_url(base: str, panel_id: int) -> str:
    return (f"{base.rstrip('/')}/d-solo/{GRAFANA_DASHBOARD_UID}/filinglens"
            f"?orgId=1&panelId={panel_id}&theme=light&refresh=10s")
