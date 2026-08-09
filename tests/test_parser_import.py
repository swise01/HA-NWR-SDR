"""Ensure a clean parser environment has every declared dependency."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def test_parser_imports() -> None:
    parser_path = Path(__file__).parents[1] / "pi" / "nwr_parser.py"
    spec = importlib.util.spec_from_file_location("nwr_parser", parser_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.TOPIC_ROOT == "nwr"


def test_parser_clears_expired_retained_alert() -> None:
    parser_path = Path(__file__).parents[1] / "pi" / "nwr_parser.py"
    spec = importlib.util.spec_from_file_location("nwr_parser_retained", parser_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.pub = Mock()
    module.on_message(
        None,
        None,
        SimpleNamespace(
            topic="nwr/alert/same",
            payload=json.dumps(
                {
                    "issue_expiry_utc": "2000-01-01T00:00:00+00:00",
                    "raw": "expired",
                }
            ).encode(),
        ),
    )
    module.pub.assert_called_once_with("alert/same", "", retain=True, qos=1)
