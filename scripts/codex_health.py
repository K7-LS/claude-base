# -*- coding: utf-8 -*-
"""Read-only health-check среды Codex (ТЗ Codex, хаб-задачи 2026-08-27).

Проверяет: агентские TOML, live-каталог skills, плагины, feature-флаг,
hooks, personal marketplace и зеркало whitelist. Ничего не меняет.

Запуск: python ~/.claude/scripts/codex_health.py
Exit: 0 — все секции PASS; 1 — есть FAIL.
"""
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

HOME = Path.home()
REQUIRED_PLUGINS = [
    "bim-cad-workflows@personal",
    "construction-documents@personal",
    "project-controls@personal",
]

results = []


def section(name):
    def wrap(fn):
        def run():
            try:
                detail = fn()
                results.append((name, True, detail or ""))
            except Exception as e:
                results.append((name, False, str(e)))
        return run
    return wrap


def codex(*args) -> str:
    out = subprocess.run(["codex", *args], capture_output=True, text=True,
                         encoding="utf-8", errors="replace", timeout=120)
    return out.stdout + out.stderr


@section("agents")
def check_agents():
    config = tomllib.loads((HOME / ".codex" / "config.toml").read_text(encoding="utf-8"))
    seen = set()
    for path in sorted((HOME / ".codex" / "agents").glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        for key in ("name", "description", "developer_instructions"):
            assert data.get(key), f"{path.name}: нет {key}"
        assert data["name"] not in seen, f"дубль имени роли: {data['name']}"
        seen.add(data["name"])
    for name, item in config.get("agents", {}).items():
        if not isinstance(item, dict) or "config_file" not in item:
            continue
        p = HOME / ".codex" / item["config_file"]
        data = tomllib.loads(p.read_text(encoding="utf-8"))
        assert data["name"] == name, f"{name}: имя в config_file не совпадает"
    return f"{len(seen)} профилей"


@section("skills")
def check_skills():
    bad = []
    for d in (HOME / ".agents" / "skills").iterdir():
        if not d.is_dir() or re.search(r"backup|^_bak-", d.name):
            continue
        if not (d / "SKILL.md").is_file():
            bad.append(d.name)
    assert not bad, f"без SKILL.md: {bad}"
    return "live-каталог чист"


@section("plugins")
def check_plugins():
    listing = codex("plugin", "list")
    missing = []
    for req in REQUIRED_PLUGINS:
        m = re.search(rf"^{re.escape(req)}\s+(\S[^\r\n]*?)\s{{2,}}\S+\s{{2,}}(\S.*)$",
                      listing, re.M)
        if not m or "installed, enabled" not in m.group(1):
            missing.append(req)
            continue
        src = m.group(2).strip()
        if not Path(src).exists():
            missing.append(req + " (путь источника не существует)")
    assert not missing, f"проблемы: {missing}"
    return f"{len(REQUIRED_PLUGINS)} обязательных installed+enabled"


@section("feature-flag")
def check_flag():
    out = codex("features", "list")
    assert re.search(r"^default_mode_request_user_input\s+.*\btrue\b", out, re.M), \
        "default_mode_request_user_input не true (эффективное значение)"
    return "вопросы в Default mode включены"


@section("hooks")
def check_hooks():
    config = tomllib.loads((HOME / ".codex" / "config.toml").read_text(encoding="utf-8"))
    assert config.get("features", {}).get("hooks") is True, "features.hooks != true"
    hooks = json.loads((HOME / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    text = json.dumps(hooks, ensure_ascii=False)
    assert "update-session-tools" not in text, "updater-маркер в hooks.json (снят 2026-08-27)"
    for m in re.finditer(r'"commandWindows":\s*"([^"]+)"', text):
        for token in re.findall(r'[A-Za-z]:\\\\[^" ]+\.ps1|\$env:USERPROFILE\\\\[^" ]+\.ps1',
                                m.group(1)):
            p = Path(token.replace("$env:USERPROFILE", str(HOME)).replace("\\\\", "\\"))
            assert p.exists(), f"скрипт хука не существует: {p}"
    return "hooks валидны, updater отсутствует"


@section("marketplace")
def check_marketplace():
    mp = json.loads((HOME / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8"))
    bad = []
    for p in mp.get("plugins", []):
        src = p.get("source", {})
        if src.get("source") == "local":
            resolved = HOME / src["path"].lstrip("./").replace("/", "\\")
            if not resolved.exists():
                bad.append(f"{p['name']} -> {resolved}")
    assert not bad, f"нерезолвящиеся пути: {bad}"
    return f"{len(mp.get('plugins', []))} записей, пути резолвятся"


@section("whitelist-mirror")
def check_whitelist():
    local = HOME / ".codex" / "base" / "mcp-whitelist.json"
    canon = HOME / ".claude" / "codex-layer" / "mcp-whitelist.json"
    assert local.exists(), "зеркало ~/.codex/base/mcp-whitelist.json отсутствует (нужен sync)"
    if canon.exists():
        assert local.read_text(encoding="utf-8") == canon.read_text(encoding="utf-8"), \
            "зеркало отстало от канона (нужен sync)"
    return "зеркало актуально"


def main() -> int:
    for fn in [check_agents, check_skills, check_plugins, check_flag,
               check_hooks, check_marketplace, check_whitelist]:
        fn()
    failed = False
    for name, ok, detail in results:
        mark = "PASS" if ok else "FAIL"
        print(f"[{mark}] {name}: {detail}")
        failed |= not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
