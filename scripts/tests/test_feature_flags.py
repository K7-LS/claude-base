# -*- coding: utf-8 -*-
"""ensure_feature_flags: ключ-в-существующую-таблицу, без второй [features]."""
import json
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from codex_sync import ensure_feature_flags  # noqa: E402

FLAGS = {"features": {"default_mode_request_user_input": True}}


def make_home(tmp_path: Path, config_text: str) -> Path:
    (tmp_path / ".claude" / "codex-layer").mkdir(parents=True)
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".claude" / "codex-layer" / "feature-flags.json").write_text(
        json.dumps(FLAGS), encoding="utf-8")
    (tmp_path / ".codex" / "config.toml").write_text(config_text, encoding="utf-8")
    return tmp_path


def test_adds_missing_key_into_existing_table(tmp_path):
    home = make_home(tmp_path, "model = \"x\"\n\n[features]\nhooks = true\n\n[desktop]\na = 1\n")
    assert ensure_feature_flags(home) is True
    cfg = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["features"]["default_mode_request_user_input"] is True
    assert cfg["features"]["hooks"] is True          # существующее не тронуто
    assert cfg["desktop"]["a"] == 1                  # соседняя таблица цела


def test_does_not_override_explicit_user_value(tmp_path):
    home = make_home(tmp_path, "[features]\ndefault_mode_request_user_input = false\n")
    assert ensure_feature_flags(home) is False       # ключ есть — не трогаем
    cfg = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["features"]["default_mode_request_user_input"] is False


def test_creates_table_when_absent(tmp_path):
    home = make_home(tmp_path, "model = \"x\"\n")
    assert ensure_feature_flags(home) is True
    cfg = tomllib.loads((home / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["features"]["default_mode_request_user_input"] is True
