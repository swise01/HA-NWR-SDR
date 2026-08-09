"""Ensure a clean parser environment has every declared dependency."""

from __future__ import annotations

import importlib.util
import json
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


def _load_parser(name: str):
    parser_path = Path(__file__).parents[1] / "pi" / "nwr_parser.py"
    spec = importlib.util.spec_from_file_location(name, parser_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parser_imports() -> None:
    module = _load_parser("nwr_parser")
    assert module.TOPIC_ROOT == "nwr"


def test_parser_clears_expired_retained_alert() -> None:
    module = _load_parser("nwr_parser_retained")
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


def test_parser_queues_valid_command_once_and_ignores_retained() -> None:
    module = _load_parser("nwr_parser_commands")
    module.pub = Mock()
    payload = json.dumps(
        {"command": "set_frequency", "value": "162.475M", "request_id": "abc"}
    ).encode()
    message = SimpleNamespace(
        topic="nwr/control/command", payload=payload, retain=False
    )

    module.on_message(None, None, message)
    module.on_message(None, None, message)
    module.on_message(
        None,
        None,
        SimpleNamespace(topic=message.topic, payload=payload, retain=True),
    )

    assert module._control_queue.get_nowait() == (
        "set_frequency",
        "162.475M",
        "abc",
    )
    assert module._control_queue.empty()
    module.pub.assert_not_called()


def test_parser_rejects_unknown_command() -> None:
    module = _load_parser("nwr_parser_reject")
    module.pub = Mock()
    module.on_message(
        None,
        None,
        SimpleNamespace(
            topic="nwr/control/command",
            payload=b'{"command":"shell","value":"reboot","request_id":"bad"}',
            retain=False,
        ),
    )
    assert module._control_queue.empty()
    assert module._control_state["last_result"] == "error"
    assert module._control_state["message"] == "unsupported command"


def test_parser_rejects_restart_with_a_value() -> None:
    module = _load_parser("nwr_parser_restart_value")
    module.pub = Mock()
    module.on_message(
        None,
        None,
        SimpleNamespace(
            topic="nwr/control/command",
            payload=b'{"command":"restart","value":"now","request_id":"bad"}',
            retain=False,
        ),
    )
    assert module._control_queue.empty()
    assert module._control_state["message"] == "restart does not accept a value"


def test_parser_applies_and_persists_bounded_settings(tmp_path: Path) -> None:
    module = _load_parser("nwr_parser_persist")
    module.pub = Mock()
    state_path = tmp_path / "nwr" / "control.json"

    assert module._apply_control_command("set_gain", 31.24, "gain-1", state_path)

    saved = json.loads(state_path.read_text())
    assert saved == {"frequency": "162.550M", "gain": 31.2, "ppm": 0}
    assert stat.S_IMODE(state_path.stat().st_mode) == 0o600
    assert module._load_control_state(state_path)["gain"] == 31.2
    module.pub.assert_called_with(
        "control/state", module._control_state, retain=True, qos=1
    )


def test_parser_rejects_out_of_range_setting_without_mutation(tmp_path: Path) -> None:
    module = _load_parser("nwr_parser_range")
    module.pub = Mock()
    before = dict(module._control_state)

    assert not module._apply_control_command(
        "set_ppm", 1000, "ppm-bad", tmp_path / "control.json"
    )

    assert module._control_state["ppm"] == before["ppm"]
    assert module._control_state["last_result"] == "error"
    assert not (tmp_path / "control.json").exists()
