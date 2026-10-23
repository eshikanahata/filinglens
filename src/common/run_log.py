"""Append-only pipeline event log (reports/run_history.jsonl).

Stage reports are overwritten on every run, so they cannot show history. This log keeps
one JSON line per notable event (drift check, retraining, promotion, rollback) for the
console page and for Prometheus.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

HISTORY = Path("reports/run_history.jsonl")


def log_event(event: str, status: str = "ok", path: Path = HISTORY, **details: Any) -> Dict[str, Any]:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "event": event,
        "status": status,
        **details,
    }
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record) + "\n")
    return record


def read_events(path: Path = HISTORY, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Newest first. Unreadable lines are skipped, never fatal."""
    try:
        lines = Path(path).read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    events = []
    for line in lines:
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    events.reverse()
    return events[:limit] if limit else events
