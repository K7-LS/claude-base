# -*- coding: utf-8 -*-
"""Сборка фокусных плагинов Codex из канона ~/.claude/skills.

Читает codex-layer/codex-plugins.json, собирает ~/plugins/<name>/
(.codex-plugin/plugin.json + skills/) и регистрирует плагины в personal
marketplace ~/.agents/plugins/marketplace.json. Идемпотентно: тело плагина
пересобирается целиком (канон — skills базы), marketplace только дополняется.

Запуск: python ~/.claude/scripts/build_codex_plugins.py [имя ...]
Без аргументов — все плагины из codex-plugins.json.
"""
import json
import shutil
import sys
from pathlib import Path

HOME = Path.home()
CANON_SKILLS = HOME / ".claude" / "skills"
CONFIG = HOME / ".claude" / "codex-layer" / "codex-plugins.json"
PLUGINS_ROOT = HOME / "plugins"          # путь, который реально резолвит CLI
MARKETPLACE = HOME / ".agents" / "plugins" / "marketplace.json"

IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")


def build_plugin(name: str, spec: dict) -> None:
    missing = [s for s in spec["skills"] if not (CANON_SKILLS / s / "SKILL.md").exists()]
    if missing:
        raise SystemExit(f"[build] {name}: в каноне нет скиллов: {missing}")
    root = PLUGINS_ROOT / name
    skills_dir = root / "skills"
    if skills_dir.exists():
        shutil.rmtree(skills_dir)
    for s in spec["skills"]:
        shutil.copytree(CANON_SKILLS / s, skills_dir / s, ignore=IGNORE)
    # Схемы данных членов-скиллов поднимаются в корень плагина (решение Codex,
    # 2026-08-28): plugin-level канон схем, коллизия имён — ошибка сборки.
    schemas_dir = root / "schemas"
    if schemas_dir.exists():
        shutil.rmtree(schemas_dir)
    for s in spec["skills"]:
        source = CANON_SKILLS / s / "schemas"
        if not source.is_dir():
            continue
        for f in sorted(source.glob("*.json")):
            schemas_dir.mkdir(parents=True, exist_ok=True)
            target = schemas_dir / f.name
            if target.exists():
                raise SystemExit(
                    f"[build] {name}: коллизия схем {f.name} (скилл {s})")
            shutil.copy2(f, target)
    (root / ".codex-plugin").mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": spec["version"],
        "description": spec["description"],
        "author": {"name": "K7 base"},
        "skills": "./skills/",
        "interface": {
            "displayName": spec["displayName"],
            "shortDescription": spec["description"],
            "longDescription": spec["description"]
            + " Собран из канона claude-base скриптом build_codex_plugins.py.",
            "developerName": "K7 base",
            "category": "Productivity",
            "capabilities": [],
            "defaultPrompt": f"Помоги с задачей через {spec['displayName']}.",
        },
    }
    (root / ".codex-plugin" / "plugin.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[build] {name}: {len(spec['skills'])} скилл(ов) -> {root}")


def register_in_marketplace(names: list) -> None:
    mp = json.loads(MARKETPLACE.read_text(encoding="utf-8"))
    known = {p["name"] for p in mp.get("plugins", [])}
    added = 0
    for name in names:
        if name in known:
            continue
        mp["plugins"].append({
            "name": name,
            "source": {"source": "local", "path": f"./plugins/{name}"},
            "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
            "category": "Productivity",
        })
        added += 1
    if added:
        MARKETPLACE.write_text(
            json.dumps(mp, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[marketplace] записей добавлено: {added}")


def main() -> int:
    cfg = json.loads(CONFIG.read_text(encoding="utf-8"))["plugins"]
    names = sys.argv[1:] or list(cfg)
    for name in names:
        if name not in cfg:
            raise SystemExit(f"[build] неизвестный плагин: {name} (есть: {list(cfg)})")
        build_plugin(name, cfg[name])
    register_in_marketplace(names)
    return 0


if __name__ == "__main__":
    sys.exit(main())
