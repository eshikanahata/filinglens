"""Shared helpers: parameter loading and logging setup."""

import logging
import os
from pathlib import Path
from typing import Any, Dict

import yaml


def load_params(path: str = "params.yaml") -> Dict[str, Any]:
    """Load the DVC-tracked parameter file."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def setup_logging(name: str, log_dir: str = "logs", level: int = logging.INFO) -> None:
    """Log to console and to logs/<name>.log (the log folder is git-ignored)."""
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
    root = logging.getLogger()
    root.setLevel(level)
    if root.handlers:
        return
    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(fmt))
    logfile = logging.FileHandler(os.path.join(log_dir, f"{name}.log"), encoding="utf-8")
    logfile.setFormatter(logging.Formatter(fmt))
    root.addHandler(console)
    root.addHandler(logfile)
