"""Validate reusable configuration examples."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).parents[1]


def test_dashboard_example_is_valid_yaml() -> None:
    dashboard = yaml.safe_load(
        (ROOT / "examples" / "dashboards" / "nwr-overview.yaml").read_text()
    )
    assert dashboard["title"] == "NOAA Weather Radio"
    assert dashboard["views"][0]["path"] == "overview"
    cards = dashboard["views"][0]["cards"]
    assert any(card.get("title") == "Radio receiver control" for card in cards)
