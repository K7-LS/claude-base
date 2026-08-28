# -*- coding: utf-8 -*-
"""Контракты канона карты понимания (зеркальное решение Claude+Codex, 2026-08-28):
schema v1, map_store (plan/apply, CAS, backup, atomic), рендеры с экранированием,
markdown-фолбэк, схемы в корне плагина."""
import json
import pathlib
import sys

import pytest

SKILL = pathlib.Path.home() / ".claude" / "skills" / "understanding-map"
TOOLS = SKILL / "tools"
sys.path.insert(0, str(TOOLS))

import map_store  # noqa: E402
import render_map  # noqa: E402

SAMPLE = json.loads(
    (SKILL / "examples" / "canonical-sample.json").read_text(encoding="utf-8"))


def _sample():
    return json.loads(json.dumps(SAMPLE))


# ───────────────────────────── схема и валидация ─────────────────────────────

def test_canonical_sample_is_valid():
    assert map_store.validate_map(_sample()) == []


def test_sample_matches_json_schema_when_jsonschema_available():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(
        (SKILL / "schemas" / "understanding-map.schema.json")
        .read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(_sample())


@pytest.mark.parametrize("mutate,fragment", [
    (lambda d: d.pop("goal"), "goal"),
    (lambda d: d.pop("next_step"), "next_step"),
    (lambda d: d.update(review_state="approved"), "review_state"),
    (lambda d: d["understanding"].append({"id": "u1", "title": "дубль"}), "дубль"),
    (lambda d: d["understanding"][0].update(source_ids=["нет-такого"]), "неизвестный"),
    (lambda d: d["sources"].append(
        {"id": "s3", "kind": "file", "ref": "C:/абсолютный/путь.md"}), "относительным"),
    (lambda d: d.update(revision=0), "revision"),
])
def test_validate_map_rejects_contract_violations(mutate, fragment):
    doc = _sample()
    mutate(doc)
    errors = map_store.validate_map(doc)
    assert errors and any(fragment in e for e in errors)


def test_unknown_fields_are_allowed_and_survive_apply(tmp_path):
    doc = _sample()
    doc["x_custom"] = {"будущее": "поле"}
    assert map_store.validate_map(doc) == []
    data = tmp_path / "new.json"
    data.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    assert map_store.cmd_apply(tmp_path, data, None) == 0
    written = json.loads(
        (tmp_path / "understanding-map.json").read_text(encoding="utf-8"))
    assert written["x_custom"] == {"будущее": "поле"}


# ───────────────────────────── map_store: жизненный цикл ─────────────────────────────

def _write_data(tmp_path, doc, name="new.json"):
    p = tmp_path / name
    p.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    return p


def test_create_update_cas_backup_atomic(tmp_path, capsys):
    data = _write_data(tmp_path, _sample())
    # create: ревизию назначает store
    assert map_store.cmd_apply(tmp_path, data, None) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "APPLIED" and out["new_revision"] == 1
    disk = tmp_path / "understanding-map.json"
    assert json.loads(disk.read_text(encoding="utf-8"))["revision"] == 1

    # update без base-revision — MAP_CONFLICT, файл не тронут
    before = disk.read_bytes()
    assert map_store.cmd_apply(tmp_path, data, None) == 3
    assert json.loads(capsys.readouterr().out)["status"] == "MAP_CONFLICT"
    assert disk.read_bytes() == before

    # update с неверной ревизией — MAP_CONFLICT
    assert map_store.cmd_apply(tmp_path, data, 7) == 3
    capsys.readouterr()
    assert disk.read_bytes() == before

    # корректный CAS: revision 1 → 2, backup прежней версии создан
    doc2 = _sample()
    doc2["goal"] = "Обновлённая цель"
    data2 = _write_data(tmp_path, doc2, "new2.json")
    assert map_store.cmd_apply(tmp_path, data2, 1) == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["new_revision"] == 2
    written = json.loads(disk.read_text(encoding="utf-8"))
    assert written["revision"] == 2 and written["goal"] == "Обновлённая цель"
    backup = tmp_path / "understanding-map.json.bak-rev1"
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8"))["revision"] == 1
    assert not list(tmp_path.glob("*.tmp-map-store"))


def test_plan_is_dry_run(tmp_path, capsys):
    data = _write_data(tmp_path, _sample())
    assert map_store.cmd_plan(tmp_path, data, None) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "READY" and out["action"] == "create"
    assert out["dry_run"] is True and out["counts"]["understanding"] == 1
    assert not (tmp_path / "understanding-map.json").exists()


def test_newer_schema_on_disk_is_read_only(tmp_path, capsys):
    disk = tmp_path / "understanding-map.json"
    future = {"schema_version": 2, "revision": 5, "будущее": True}
    disk.write_text(json.dumps(future, ensure_ascii=False), encoding="utf-8")
    before = disk.read_bytes()
    assert map_store.cmd_read(tmp_path) == 4
    assert json.loads(capsys.readouterr().out)["status"] == "UNSUPPORTED_SCHEMA"
    data = _write_data(tmp_path, _sample())
    assert map_store.cmd_apply(tmp_path, data, 5) == 4
    assert json.loads(capsys.readouterr().out)["status"] == "UNSUPPORTED_SCHEMA"
    assert disk.read_bytes() == before                      # файл не переписан


def test_missing_map_is_normal(tmp_path, capsys):
    assert map_store.cmd_read(tmp_path) == 5
    assert json.loads(capsys.readouterr().out)["status"] == "NO_MAP"


# ───────────────────────────── рендеры: канон и экранирование ─────────────────────────────

HOSTILE = "<script>alert('xss')</script>"


def _hostile_doc():
    doc = _sample()
    doc["title"] = f"Заголовок {HOSTILE}"
    doc["goal"] = f"Цель {HOSTILE}"
    doc["understanding"][0]["title"] = f"П {HOSTILE}"
    doc["understanding"][0]["detail"] = f"Д {HOSTILE}"
    doc["decisions"][0]["title"] = f"Р {HOSTILE}"
    doc["sources"][0]["locator"] = HOSTILE
    return doc


@pytest.mark.parametrize("builder", ["widget", "standalone"])
def test_canonical_html_modes_escape_everything(builder):
    view = render_map.canonical_to_view(_hostile_doc())
    out = (render_map.build_widget(view) if builder == "widget"
           else render_map.build_standalone(view))
    assert HOSTILE not in out
    assert "&lt;script&gt;" in out


def test_markdown_mode_renders_canonical_sections():
    out = render_map.build_markdown(_sample())
    for fragment in ("# Что я понял", "## Понято", "## Допущения — проверь",
                     "## Пробелы — решаем", "## Решения (snapshot)",
                     "## Следующий шаг", "## Источники", "rev 1",
                     "DECISIONS.md#D-001", "FACTS.md"):
        assert fragment in out
    assert "<div" not in out


def test_canonical_view_maps_zones_and_stamp():
    view = render_map.canonical_to_view(_sample())
    zones = [i["zone"] for i in view["items"]]
    assert zones == ["ok", "as", "pe"]
    assert any("rev 1" in c["v"] for c in view["stamp"])
    assert any(c["k"] == "Статус сверки" and c["soft"] for c in view["stamp"])
    assert view["decisions"][0]["ln"] == "d1"


def test_legacy_view_format_still_passes_markup_through():
    # Прежний session-local контракт (доверенный вход) сохранён осознанно.
    legacy = {"title": "T", "goal": "Цель <b>жирным</b>",
              "items": [{"zone": "ok", "title": "x", "detail": "<b>y</b>"}]}
    assert not render_map.is_canonical(legacy)
    out = render_map.build_standalone(legacy)
    assert "<b>жирным</b>" in out


# ───────────────────────────── сборка плагина: schemas/ ─────────────────────────────

def test_plugin_builder_lifts_member_schemas_to_plugin_root(tmp_path, monkeypatch):
    scripts = pathlib.Path.home() / ".claude" / "scripts"
    sys.path.insert(0, str(scripts))
    import build_codex_plugins as bcp

    canon = tmp_path / "skills"
    (canon / "map-skill" / "schemas").mkdir(parents=True)
    (canon / "map-skill" / "SKILL.md").write_text("---\nname: map-skill\n---\n",
                                                  encoding="utf-8")
    (canon / "map-skill" / "schemas" / "m.schema.json").write_text("{}",
                                                                   encoding="utf-8")
    (canon / "plain-skill").mkdir(parents=True)
    (canon / "plain-skill" / "SKILL.md").write_text("---\nname: plain-skill\n---\n",
                                                    encoding="utf-8")
    monkeypatch.setattr(bcp, "CANON_SKILLS", canon)
    monkeypatch.setattr(bcp, "PLUGINS_ROOT", tmp_path / "plugins")

    spec = {"skills": ["map-skill", "plain-skill"], "version": "0.0.1",
            "description": "t", "displayName": "T"}
    bcp.build_plugin("demo", spec)
    root = tmp_path / "plugins" / "demo"
    assert (root / "schemas" / "m.schema.json").is_file()          # plugin-root
    assert (root / "skills" / "map-skill" / "schemas" / "m.schema.json").is_file()

    # коллизия имён схем между скиллами — ошибка сборки
    (canon / "plain-skill" / "schemas").mkdir()
    (canon / "plain-skill" / "schemas" / "m.schema.json").write_text("{}",
                                                                     encoding="utf-8")
    with pytest.raises(SystemExit, match="коллизия"):
        bcp.build_plugin("demo", spec)
