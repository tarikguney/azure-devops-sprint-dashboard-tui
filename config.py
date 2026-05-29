"""User configuration for the ADO dashboard.

Stores Azure DevOps connection details in a per-user JSON file so they
don't have to be hardcoded. On first run, the dashboard prompts for these
values and writes them here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path

CONFIG_DIR = Path.home() / ".ado-dashboard"
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    organization: str
    project: str
    team: str
    user_email: str

    @property
    def org_url(self) -> str:
        return f"https://dev.azure.com/{self.organization}"

    @property
    def work_item_base_url(self) -> str:
        return f"{self.org_url}/{self.project}/_workitems/edit"


_active: AppConfig | None = None


def load_config() -> AppConfig | None:
    """Load config from disk, or None if it doesn't exist or is incomplete."""
    if not CONFIG_PATH.exists():
        return None
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    required = ("organization", "project", "team", "user_email")
    if not all(data.get(k) for k in required):
        return None
    return AppConfig(
        organization=data["organization"],
        project=data["project"],
        team=data["team"],
        user_email=data["user_email"],
    )


def save_config(cfg: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), indent=2),
        encoding="utf-8",
    )


def set_active(cfg: AppConfig) -> None:
    global _active
    _active = cfg


def get_active() -> AppConfig:
    if _active is None:
        raise RuntimeError(
            "No active configuration. Call set_active() after load_config() "
            "or after a first-run setup."
        )
    return _active
