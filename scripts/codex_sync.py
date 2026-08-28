# -*- coding: utf-8 -*-
"""Генератор среды Codex из канона ~/.claude.

Запуск: python codex_sync.py [sync|check|diff|mcp] [--dry-run]
        [--force-overwrite KEY|all]
"""
import hashlib
import json
import re
import sys
import tomllib
from pathlib import Path
from jsonschema import Draft202012Validator
from codex_mcp_overlay import OverlayError, load_overlay_names, normalize_overlay_names, overlay_path

BEGIN = "# >>> claude-base managed >>>"
END = "# <<< claude-base managed <<<"


def _is_codex_runtime_table(name: str) -> bool:
    """Таблицы, которыми владеет Codex App, а не канонический синк.
    cua_repl — App-owned (решение Codex, приёмка 2026-08-28): Desktop сам
    вписывает секцию с версионным WindowsApps-путём, в канон её не включаем."""
    return (name == "memories" or name == "hooks.state" or name.startswith("hooks.state.")
            or name == "mcp_servers.cua_repl" or name.startswith("mcp_servers.cua_repl."))


def _split_codex_runtime_tables(text: str) -> tuple[str, str]:
    """Отделить runtime-секции App, сохранив их текст без семантической правки."""
    headers = list(re.finditer(r"(?m)^\[(?P<name>[^\]]+)\][ \t]*$", text))
    if not headers:
        return text, ""
    kept, runtime = [], []
    cursor = 0
    for i, header in enumerate(headers):
        start = header.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        kept.append(text[cursor:start])
        part = text[start:end]
        if _is_codex_runtime_table(header.group("name")):
            runtime.append(part.strip())
        else:
            kept.append(part)
        cursor = end
    return "".join(kept), "\n\n".join(part for part in runtime if part)

def _dedupe_codex_runtime_tables(runtime: str) -> str:
    """Схлопнуть дубли runtime-таблиц (App мог записать секцию и внутрь
    managed-блока, и снаружи): последняя копия побеждает, порядок — по
    первому появлению; дубль таблицы в TOML иначе невалиден."""
    if not runtime:
        return runtime
    headers = list(re.finditer(r"(?m)^\[(?P<name>[^\]]+)\][ \t]*$", runtime))
    if len(headers) <= 1:
        return runtime
    order, by_name = [], {}
    for i, header in enumerate(headers):
        start = header.start()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(runtime)
        name = header.group("name")
        if name not in by_name:
            order.append(name)
        by_name[name] = runtime[start:end].strip()
    return "\n\n".join(by_name[name] for name in order)

def apply_managed_block(existing: str, payload: str) -> str:
    block = f"{BEGIN}\n{payload.rstrip()}\n{END}\n"
    pattern = re.compile(re.escape(BEGIN) + r"\n(.*?)\n?" + re.escape(END) + r"\n?", re.S)
    old_payloads = [m.group(1) for m in pattern.finditer(existing)]
    stripped = pattern.sub("", existing)          # убрать ВСЕ старые блоки
    stripped, runtime = _split_codex_runtime_tables(stripped)
    for old_payload in old_payloads:
        _, inside_runtime = _split_codex_runtime_tables(old_payload)
        if inside_runtime:
            runtime = "\n\n".join(part for part in (runtime, inside_runtime) if part)
    runtime = _dedupe_codex_runtime_tables(runtime)
    if not stripped.strip():
        return block + ("\n" + runtime.rstrip() + "\n" if runtime else "")
    sep = "" if stripped.endswith("\n\n") else ("\n" if stripped.endswith("\n") else "\n\n")
    return stripped + sep + block + ("\n" + runtime.rstrip() + "\n" if runtime else "")

def _t(v: str) -> str:
    # TOML literal string для простых значений (Windows-пути без экранирования);
    # апостроф/перевод строки в literal невозможны — таким значениям basic string
    s = str(v)
    if "'" not in s and "\n" not in s:
        return "'" + s + "'"
    esc = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return '"' + esc + '"'

def render_mcp_toml(mcp_servers: dict, allow: list, bridge=frozenset()) -> str:
    out = []
    for name in sorted(mcp_servers):
        if name not in allow:
            continue
        cfg = mcp_servers[name]
        if "url" in cfg:                # [I1] remote (http/sse) — без command/args
            out.append(f"[mcp_servers.{name}]")
            out.append(f"url = {_t(cfg['url'])}")
            out.append("")
            continue
        if "command" not in cfg:        # [I1] ни command, ни url — пропуск с предупреждением
            print(f"[codex_sync] warn: MCP-сервер {name} без command и без url (type={cfg.get('type', '?')}) — пропущен", file=sys.stderr)
            continue
        out.append(f"[mcp_servers.{name}]")
        out.append(f"command = {_t(cfg['command'])}")
        args = cfg.get("args", [])
        out.append("args = [" + ", ".join(_t(a) for a in args) + "]")
        if name in bridge:              # мост по требованию: не ронять десктоп и ждать тяжёлый старт
            out.append("required = false")
            out.append("startup_timeout_sec = 60")
        env = cfg.get("env") or {}
        if env:
            out.append(f"[mcp_servers.{name}.env]")
            for k in sorted(env):
                out.append(f"{k} = {_t(env[k])}")
        out.append("")
    return "\n".join(out)

def render_base_tables(home: Path) -> str:
    """Эталонные секции base.toml для managed-блока. Только таблицы; секции,
    заданные пользователем вне блока, пропускаются с предупреждением
    (дубль таблицы = невалидный TOML)."""
    p = home / ".claude" / "codex-layer" / "base.toml"
    if not p.exists():
        return ""
    text = p.read_text(encoding="utf-8")
    parsed = tomllib.loads(text)
    toplevel = [k for k, v in parsed.items() if not isinstance(v, dict)]
    if toplevel:
        raise ValueError(f"base.toml: top-level ключи запрещены (уедут в чужую таблицу): {toplevel}")
    cfg = home / ".codex" / "config.toml"
    outside = cfg.read_text(encoding="utf-8") if cfg.exists() else ""
    outside = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S).sub("", outside)
    try:
        tomllib.loads(outside)
        user_tables = set(re.findall(r"(?m)^\s*\[([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$", outside))
    except tomllib.TOMLDecodeError as e:
        print(f"[codex_sync] warn: config.toml вне managed-блока не парсится ({e}) — фильтр коллизий пропущен",
              file=sys.stderr)
        user_tables = set()
    blocks, name, current = [], None, []
    for line in text.splitlines():
        m = re.match(r"\[([A-Za-z0-9_.-]+)\]", line.strip())
        if m:
            if name is not None:
                blocks.append((name, current))
            name, current = m.group(1), [line]
        elif name is not None:
            current.append(line)
    if name is not None:
        blocks.append((name, current))
    kept = []
    for tname, lines in blocks:
        if tname in user_tables:
            print(f"[codex_sync] warn: секция [{tname}] задана вне managed-блока — эталон пропущен",
                  file=sys.stderr)
            continue
        kept.append("\n".join(lines).rstrip())
    return "\n\n".join(kept)

def render_skills_toml(manifest: dict, skills_dir: Path) -> str:
    """не используется main() с 2026-07-14 — skills.config не работает в десктоп-сборке,
    оставлена для будущих версий"""
    out = []
    for name in manifest.get("enable", []):
        d = skills_dir / name
        if not (d / "SKILL.md").exists():
            print(f"[codex_sync] warn: скилл {name} не найден в {skills_dir}", file=sys.stderr)
            continue
        out.append("[[skills.config]]")
        out.append(f"path = {_t(str(d))}")
        out.append("enabled = true")
        out.append("")
    return "\n".join(out)

def _is_junction(p: Path) -> bool:
    """Проверить, является ли путь Windows directory junction или symlink."""
    import os
    try:
        if not p.is_dir():
            return False
        # Windows symlink (os.path.islink работает, но может не ловить все junction'ы)
        # Альтернативный способ: проверить атрибут файла FILE_ATTRIBUTE_REPARSE_POINT (0x400)
        stat_result = os.stat(p, follow_symlinks=False)
        return bool(stat_result.st_file_attributes & 0x400) or os.path.islink(str(p))
    except (OSError, AttributeError):
        return False

def _junction_points_to(dst: Path, source: Path) -> bool:
    try:
        return _is_junction(dst) and dst.resolve(strict=True) == source.resolve(strict=True)
    except OSError:
        return False

def validate_skills_manifest(manifest: dict, skills_dir: Path) -> None:
    """Каждый skill канона явно включён или осознанно пропущен с причиной."""
    enabled = manifest.get("enable", [])
    skipped = manifest.get("skip_reason", {})
    if not isinstance(enabled, list) or any(not isinstance(name, str) for name in enabled):
        raise ValueError("skills-manifest.enable должен быть списком строк")
    if not isinstance(skipped, dict) or any(
        not isinstance(name, str) or not isinstance(reason, str) or not reason.strip()
        for name, reason in skipped.items()
    ):
        raise ValueError("skills-manifest.skip_reason должен быть map имя→непустая причина")
    overlap = set(enabled) & set(skipped)
    if overlap:
        raise ValueError(f"скилл одновременно enable и skip_reason: {', '.join(sorted(overlap))}")
    actual = {child.name for child in skills_dir.iterdir()
              if child.is_dir() and (child / "SKILL.md").is_file()}
    accounted = set(enabled) | set(skipped)
    missing = actual - accounted
    stale = accounted - actual
    if missing or stale:
        raise ValueError(
            "skills-manifest не соответствует канону: "
            f"не классифицированы={sorted(missing)}, отсутствуют={sorted(stale)}"
        )

def ensure_skill_junctions(manifest: dict, skills_dir: Path, agents_skills_dir: Path) -> list:
    """Junction на каждый скилл из манифеста в ~/.agents/skills (стандартный путь Codex).
    Возвращает список созданных. Чужие папки (не junction на skills_dir) не трогает."""
    import subprocess
    agents_skills_dir.mkdir(parents=True, exist_ok=True)
    enabled = [n for n in manifest.get("enable", []) if (skills_dir / n / "SKILL.md").exists()]
    for n in manifest.get("enable", []):
        if n not in enabled:
            print(f"[codex_sync] warn: скилл {n} не найден в {skills_dir}", file=sys.stderr)
    made = []
    for n in enabled:
        dst = agents_skills_dir / n
        if dst.exists():
            if not _junction_points_to(dst, skills_dir / n):
                print(f"[codex_sync] warn: {dst} существует, но это не junction на канон — "
                      "не трогаю", file=sys.stderr)
            continue
        r = subprocess.run(["cmd", "/c", "mklink", "/J", str(dst), str(skills_dir / n)],
                           capture_output=True, text=True)
        if r.returncode == 0:
            made.append(n)
        else:
            print(f"[codex_sync] warn: junction {n} не создан: {r.stderr.strip()}", file=sys.stderr)
    # cleanup: junction'ы, указывающие в skills_dir, но выпавшие из манифеста
    for child in agents_skills_dir.iterdir():
        if child.name in enabled or not child.is_dir():
            continue
        if _is_junction(child) and (skills_dir / child.name).exists():
            try:
                child.rmdir()   # junction снимается rmdir, содержимое источника не трогается
            except OSError:
                print(f"[codex_sync] warn: не удалось удалить junction {child.name}", file=sys.stderr)
    return made

def _pwsh(script: Path) -> str:
    return f"powershell -NoProfile -ExecutionPolicy Bypass -File \"{script}\""

def render_hooks_json(home: Path) -> dict:
    # Канон hooks — решение Codex (приёмка 2026-08-28): one-way уведомление о
    # релизе + журнал моста. Старый набор не возвращать: auto-pull/push
    # противоречат one-way контуру sync-base, session-хуки сняты контрактом
    # project-memory 0.2.0, Pre/PostCompact заменён текстовым протоколом.
    # Путь журнала рендерится от home — профиль пользователя не хардкодим.
    journal = home / ".claude" / "scripts" / "interop_journal.py"
    journal_cmd = f'python "{journal}" --source codex'
    return {
        "description": "One-way Codex base release notification.",
        "hooks": {
            "SessionStart": [{
                "matcher": "^startup$",
                "hooks": [{
                    "type": "command",
                    "command": "pwsh -NoProfile -File \"$HOME/.codex/base/runtime/hooks/check_release.ps1\"",
                    "commandWindows": "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"$env:USERPROFILE\\.codex\\base\\runtime\\hooks\\check_release.ps1\"",
                    "timeout": 38,
                }],
            }],
            "PostToolUse": [{
                "matcher": "^(mcp__)?claude(/|__)",
                "hooks": [{
                    "type": "command",
                    "command": journal_cmd,
                    "commandWindows": journal_cmd,
                    "timeout": 15,
                }],
            }],
        },
    }

MODEL_MAP = {
    "opus": "gpt-5.6-sol",
    "fable": "gpt-5.6-sol",
    "sonnet": "gpt-5.6-terra",
    "haiku": "gpt-5.6-luna"
}

# TOOL_MAP переводит MCP-инструменты в описания плагинов.
TOOL_MAP = [
    (r"mcp__excel__(?:\w+|\\?\*)", "инструменты плагина spreadsheets"),
    (r"mcp__word__(?:\w+|\\?\*)", "инструменты плагина documents"),
    (r"mcp__pdf-mcp__(?:\w+|\\?\*)", "инструменты плагина pdf"),
    (r"mcp__playwright__(?:\w+|\\?\*)", "инструменты плагина browser"),
    (r"\bTask\b(?= tool| тул| \()", "spawn_agents"),
]

# [I2] маркеры записи в tools: фронтматтера — есть хотя бы один → агент пишет файлы,
# sandbox_mode не сужаем; нет ни одного (и tools вообще заданы) → read-only ревьюер.
WRITE_TOOL_MARKERS = ("Write", "Edit", "search_and_replace", "add_paragraph")

def load_capability_registry(home: Path, context=None) -> dict:
    """Загрузить единственный канон capability-адаптеров и проверить связи."""
    base = home / ".claude" / "codex-layer"
    schema = json.loads((base / "capability-registry.schema.json").read_text(encoding="utf-8"))
    data = json.loads((base / "capability-registry.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(data)
    caps = {x["capability_id"]: x for x in data["capabilities"]}
    if len(caps) != len(data["capabilities"]):
        raise ValueError("capability registry: duplicate capability_id")
    roles = {x["role_id"]: x for x in data["role_adapters"]}
    skills = {x["skill_id"]: x for x in data["skill_adapters"]}
    if len(roles) != len(data["role_adapters"]) or len(skills) != len(data["skill_adapters"]):
        raise ValueError("capability registry: duplicate role_id or skill_id")
    if len(roles) != 16 or sum(x["permission_class"] == "ro" for x in roles.values()) != 7 or sum(x["permission_class"] == "rw" for x in roles.values()) != 9:
        raise ValueError("capability registry: expected 7 RO and 9 RW role adapters")
    native = data.get("codex_native", {})
    native_roles = set(native.get("roles", []))
    native_names = native.get("agent_names", {})
    native_files = native.get("instruction_files", {})
    native_routes = native.get("tool_routes", {})
    if native_roles - set(roles):
        raise ValueError(f"capability registry: unknown Codex-native roles {sorted(native_roles - set(roles))}")
    if set(native_names) != native_roles or len(set(native_names.values())) != len(native_names):
        raise ValueError("capability registry: Codex-native agent_names must cover roles exactly and be unique")
    if set(native_files) != native_roles:
        raise ValueError("capability registry: Codex-native instruction_files must cover roles exactly")
    native_instructions = {}
    for role_id in native_roles:
        adapter = roles[role_id]
        instruction_path = (base / native_files[role_id]).resolve()
        if not instruction_path.is_relative_to(base.resolve()) or not instruction_path.is_file():
            raise ValueError(f"capability registry: missing Codex-native instructions for {role_id}")
        native_instructions[role_id] = instruction_path.read_text(encoding="utf-8").strip()
        missing_routes = [cap_id for cap_id in [*adapter["required_capabilities"], *adapter.get("optional_capabilities", [])]
                          if cap_id not in native_routes]
        if missing_routes:
            raise ValueError(f"capability registry: {role_id} has no Codex-native routes {missing_routes}")
    native["_instructions"] = native_instructions
    for item in [*data["role_adapters"], *data["skill_adapters"]]:
        optional = item.get("optional_capabilities", [])
        for cap_id in [*item["required_capabilities"], *optional]:
            cap = caps.get(cap_id)
            if cap is None:
                raise ValueError(f"capability registry: unresolved capability {cap_id}")
            if not cap["providers"] and cap["verification"]["status"] != "blocked":
                raise ValueError(f"capability registry: {cap_id} has no provider or blocked state")
        if set(item["required_capabilities"]) & set(optional):
            raise ValueError("capability registry: capability cannot be both required and optional")
    for capability in data["capabilities"]:
        for provider in capability["providers"]:
            if set(provider["environments"]) != {"claude", "codex"}:
                raise ValueError("capability registry: provider must declare Claude and Codex environments")
            if provider["enabled_by_default"] and provider["availability"] != "available":
                raise ValueError("capability registry: default provider must be available")
            if provider["availability"] == "blocked" and capability["verification"]["status"] != "blocked":
                raise ValueError("capability registry: blocked provider requires blocked capability")
    manifest = (context or _load_sync_context(home))["skills_manifest"]
    classified = set(manifest.get("enable", [])) | set(manifest.get("skip_reason", {}))
    skill_ids = set(skills)
    if classified != skill_ids or (set(manifest.get("enable", [])) & set(manifest.get("skip_reason", {}))):
        raise ValueError("capability registry: skill adapters must mirror the manifest classification (enable/skip без пересечений)")
    for skill_id, adapter in skills.items():
        enabled = skill_id in manifest["enable"]
        if (adapter["manifest_state"] == "enabled") != enabled:
            raise ValueError("capability registry: activation may only follow the manifest")
        if not enabled and adapter["skip_reason"] != manifest["skip_reason"][skill_id]:
            raise ValueError("capability registry: skipped skill must retain its manifest reason")
    patterns = set()
    for mapping in data["tool_map"]:
        if mapping["capability_id"] not in caps:
            raise ValueError(f"capability registry: TOOL_MAP references {mapping['capability_id']}")
        if mapping["raw_tool_pattern"] in patterns:
            raise ValueError("capability registry: duplicate TOOL_MAP pattern")
        patterns.add(mapping["raw_tool_pattern"])
        try:
            re.compile(mapping["raw_tool_pattern"])
        except re.error as e:
            raise ValueError(f"capability registry: invalid TOOL_MAP pattern: {e}") from e
    data["_capabilities"] = caps
    data["_roles"] = roles
    data["_skills"] = skills
    return data

def _map_raw_tools(text: str, registry: dict) -> str:
    """Заменить только известные raw MCP identifiers; неизвестный не маскировать."""
    def replace(match):
        raw = match.group(0).replace("\\*", "*")
        for item in registry["tool_map"]:
            if re.fullmatch(item["raw_tool_pattern"], raw):
                cap = registry["_capabilities"][item["capability_id"]]
                return f"capability `{cap['capability_id']}` ({cap['purpose']})"
        raise ValueError(f"capability registry: unresolved raw MCP tool {raw}")
    return re.sub(r"mcp__[A-Za-z0-9-]+__[A-Za-z0-9_*\\]+", replace, text)

def _adapt_legacy_tool_prose_for_codex(text: str) -> str:
    """Нейтрализовать в Codex-выводе только известные Claude-specific имена инструментов."""
    # Сначала заменяем целую историческую лестницу, чтобы не оставить ложный порядок провайдеров.
    web_ladder = r"`?exa`?\s*(?:→|->|/)\s*`?firecrawl`?\s*(?:→|->|/)\s*`?fetch`?\s*(?:→|->|/)\s*`?playwright`?\s*(?:→|->|/)\s*`?WebFetch`?"
    text = re.sub(
        web_ladder,
        "capability `web.search` → capability `web.fetch` / `web.extract` → capability `web.browser.interact`",
        text,
        flags=re.I,
    )
    provenance_replacements = (
        (r"(?i)exa_cntd_ru", "web_search_cntd_ru"),
        (r"(?i)firecrawl_cntd_ru", "web_extract_cntd_ru"),
        (r"(?i)playwright_cntd_ru", "web_browser_cntd_ru"),
        (r"(?i)cntd_ru_WebFetch", "cntd_ru_web_fetch"),
        (r"(?i)firecrawl_(search|scrape|extract)", r"web_extract_\1"),
        (r"(?i)memory/feedback_webfetch_reality_check\.md", "исторический feedback-файл о веб-проверке"),
        (r"(?i)Exa-first", "web-first"),
        (r"(?i)web_search_exa", "web_search"),
        (r"(?i)web_fetch_exa", "web_fetch"),
    )
    for pattern, replacement in provenance_replacements:
        text = re.sub(pattern, replacement, text)
    replacements = (
        (r"(?<![A-Za-z0-9_-])AskUserQuestion(?![A-Za-z0-9_-])", "уточняющий вопрос пользователю"),
        (r"(?<![A-Za-z0-9_-])WebFetch(?![A-Za-z0-9_-])", "capability `web.fetch`"),
        (r"(?<![A-Za-z0-9_-])exa(?![A-Za-z0-9_-])", "capability `web.search`"),
        (r"(?<![A-Za-z0-9_-])firecrawl(?![A-Za-z0-9_-])", "capability `web.extract`"),
        (r"(?<![A-Za-z0-9_-])playwright(?![A-Za-z0-9_-])", "capability `web.browser.interact`"),
        (r"(?<!web\.)(?<![A-Za-z0-9_-])fetch(?![A-Za-z0-9_-])", "capability `web.fetch`"),
        (r"(?<![A-Za-z0-9_])Bash(?![A-Za-z0-9_])", "PowerShell"),
        (r"(?<![A-Za-z0-9_])Glob(?![A-Za-z0-9_])", "rg --files"),
        (r"(?<![A-Za-z0-9_])Grep(?![A-Za-z0-9_])", "rg"),
        (r"`tail`", "`Get-Content -Tail`"),
        (r"`grep`", "`rg`"),
    )
    for pattern, replacement in replacements:
        text = re.sub(pattern, replacement, text, flags=re.I)
    return text


def _codex_native_instructions(adapter: dict, registry: dict) -> str:
    """Для выбранной роли взять короткую Codex-native инструкцию."""
    instructions = registry["codex_native"].get("_instructions", {}).get(adapter["role_id"])
    if not instructions:
        raise ValueError(f"capability registry: missing Codex-native instructions for {adapter['role_id']}")
    return instructions


def _render_codex_native_adapter(adapter: dict, registry: dict) -> str:
    routes = registry["codex_native"]["tool_routes"]
    required = [routes[capability_id] for capability_id in adapter["required_capabilities"]]
    optional = [routes[capability_id] for capability_id in adapter.get("optional_capabilities", [])]
    return (
        "\n\n[Codex-native adapter]"
        "\nrequired_tools: " + "; ".join(required) +
        "\noptional_tools: " + ("; ".join(optional) if optional else "none") +
        "\npermission_class: " + adapter["permission_class"] +
        "\ninput_contract: " + adapter["input_contract"] +
        "\noutput_contract: " + adapter["output_contract"] +
        "\nverification.codex: " + adapter["verification"].get("codex", "static") +
        "\nfallback: " + adapter["fallback"] +
        "\nhandoff: " + adapter["handoff"]
    )

def _yaml_value(front: str, key: str) -> str:
    """Значение ключа фронтматтера; block-scalar (| и >) собирается целиком:
    | — с переводами строк, > — склейка пробелом."""
    m = re.search(rf"^{key}:[ \t]*(.*)$", front, re.M)
    if not m:
        return ""
    first = m.group(1).strip()
    if first not in ("|", "|-", ">", ">-"):
        return first
    lines = []
    for line in front[m.end():].split("\n"):
        if line.strip() == "":
            lines.append("")
        elif line.startswith((" ", "\t")):
            lines.append(line.strip())
        else:
            break
    joiner = "\n" if first.startswith("|") else " "
    return joiner.join(lines).strip()

def _toml_block(s: str) -> str:
    """Многострочный TOML: literal '''...''' (бэкслэши/кавычки сырыми);
    если внутри есть ''' — basic с экранированием."""
    if "'''" not in s:
        return "'''\n" + s + "\n'''"
    esc = s.replace("\\", "\\\\").replace('"""', '""\\"')
    return '"""\n' + esc + '\n"""'

def convert_agent_md(text: str, registry: dict | None = None):
    text = text.replace("\r\n", "\n")  # CRLF-агенты реальны (5/17 в базе)
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        raise ValueError("Неверный формат: не найдена граница ---")
    front, body = m.group(1), m.group(2)
    name = _yaml_value(front, "name")
    output_name = name
    model = MODEL_MAP.get(_yaml_value(front, "model"), "gpt-5.6-terra")
    desc = _yaml_value(front, "description")
    tools = _yaml_value(front, "tools")
    if registry is None:
        for pat, repl in TOOL_MAP:
            body = re.sub(pat, repl, body)
            desc = re.sub(pat, repl, desc)
    else:
        body, desc = _map_raw_tools(body, registry), _map_raw_tools(desc, registry)
        body, desc = _adapt_legacy_tool_prose_for_codex(body), _adapt_legacy_tool_prose_for_codex(desc)
        adapter = registry["_roles"].get(name) if name else None
        if name and adapter is None:
            raise ValueError(f"capability registry: missing role adapter {name}")
        if adapter:
            if name in set(registry.get("codex_native", {}).get("roles", [])):
                output_name = registry["codex_native"]["agent_names"][name]
                body = _codex_native_instructions(adapter, registry)
                body += _render_codex_native_adapter(adapter, registry)
            else:
                body += "\n\n[Capability adapter]\nrequired: " + ", ".join(adapter["required_capabilities"])
                body += "\noptional: " + ", ".join(adapter["optional_capabilities"] or ["none"])
                body += "\npermission_class: " + adapter["permission_class"]
                body += "\ninput_contract: " + adapter["input_contract"]
                body += "\noutput_contract: " + adapter["output_contract"]
                body += "\nverification.claude: " + adapter["verification"].get("claude", "static")
                body += "\nverification.codex: " + adapter["verification"].get("codex", "static")
                body += "\nfallback: " + adapter["fallback"] + "\nhandoff: " + adapter["handoff"]
    toml_text = f"name = {_t(output_name)}\ndescription = {_t(desc)}\nmodel = {_t(model)}\n"
    if (registry is not None and name and registry["_roles"][name]["permission_class"] == "ro") or (registry is None and tools and not any(marker in tools for marker in WRITE_TOOL_MARKERS)):
        toml_text += 'sandbox_mode = "read-only"\n'   # [I2] ревьюер без Write/Edit — сузить sandbox в Codex
    toml_text += f"developer_instructions = {_toml_block(body.strip())}\n"
    return f"{name}.toml", toml_text

def collect_agent_tomls(agents_dir: Path, registry: dict | None = None) -> dict:
    """[I2] Обходит agents/*.md; пропускает не-агентские файлы (без фронтматтера
    или без name: в фронтматтере) с предупреждением вместо мусорного '.toml'."""
    out = {}
    for f in sorted(agents_dir.glob("*.md")):
        try:
            fname, toml_text = convert_agent_md(f.read_text(encoding="utf-8"), registry)
        except ValueError as e:
            if registry is not None and str(e).startswith("capability registry:"):
                raise
            print(f"[codex_sync] warn: {f.name} пропущен: {e}", file=sys.stderr)
            continue
        if fname == ".toml":
            print(f"[codex_sync] warn: {f.name} пропущен: пустое имя (нет name: в фронтматтере)", file=sys.stderr)
            continue
        out[fname] = toml_text
    return out

LANG_LINE = ("Отвечай пользователю по-русски. Код, имена файлов и идентификаторы — "
             "латиницей; комментарии в коде — по-русски.\n\n")

def render_agents_md(core: str, layer: str) -> str:
    out = LANG_LINE + core.strip() + "\n\n---\n\n" + layer.strip() + "\n"
    if len(out.encode("utf-8")) > 32768:
        raise ValueError("AGENTS.md превышает 32 KiB — сокращай ядро/слой")
    return out

def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

def _load_sync_context(home: Path) -> dict:
    """Один снимок общих входов, которые нужны нескольким фазам sync/check/diff."""
    p = home / ".claude" / "codex-layer" / "skills-manifest.json"
    text = p.read_text(encoding="utf-8")
    return {"skills_manifest_text": text, "skills_manifest": json.loads(text)}

def _read_canon(home: Path):
    """Общие входы рендера: контенты канона + mcp-срез."""
    claude = home / ".claude"
    core = (claude / "core" / "AGENTS.core.md").read_text(encoding="utf-8")
    layer = (claude / "codex-layer" / "AGENTS.codex.md").read_text(encoding="utf-8")
    wl_text = (claude / "codex-layer" / "mcp-whitelist.json").read_text(encoding="utf-8")
    mcp = json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("mcpServers", {})
    allow = json.loads(wl_text)["allow"]
    return core, layer, wl_text, mcp, allow

PROFILE_HEADER = ("# generated-by: codex_sync (канон: codex-layer/profiles/{name}.toml) — "
                  "править канон, не этот файл\n")

def render_profiles(home: Path) -> dict:
    """Профили Codex: файл канона → ~/.codex/<name>.config.toml целиком (файл наш)."""
    d = home / ".claude" / "codex-layer" / "profiles"
    out = {}
    if not d.exists():
        return out
    for f in sorted(d.glob("*.toml")):
        text = f.read_text(encoding="utf-8")
        tomllib.loads(text)      # невалидный канон профиля — падаем с понятной ошибкой
        out[f"{f.stem}.config.toml"] = PROFILE_HEADER.format(name=f.stem) + text
    return out


def render_native_agent_tables(agent_tomls: dict, registry: dict) -> str:
    """Зарегистрировать native-профили в стабильном multi-agent config Codex."""
    native = registry.get("codex_native", {})
    lines = []
    for role_id in native.get("roles", []):
        filename = f"{role_id}.toml"
        parsed = tomllib.loads(agent_tomls[filename])
        agent_name = native["agent_names"][role_id]
        if parsed["name"] != agent_name:
            raise ValueError(f"capability registry: generated agent name mismatch for {role_id}")
        lines.extend([
            f"[agents.{agent_name}]",
            f"description = {_t(parsed['description'])}",
            f"config_file = {_t('agents/' + filename)}",
            "",
        ])
    return "\n".join(lines).rstrip()

def render_target_codex(home: Path, context=None) -> dict:
    """Чистый рендер всех артефактов таргета codex: ключ → содержимое. Ничего не пишет."""
    claude = home / ".claude"
    core, layer, _, mcp, allow = _read_canon(home)
    registry_path = claude / "codex-layer" / "capability-registry.json"
    registry = load_capability_registry(home, context=context) if registry_path.exists() else None
    overlay = load_overlay(home)
    eff_allow = effective_allow(allow, overlay)
    agent_tomls = collect_agent_tomls(claude / "agents", registry)
    config_parts = [render_base_tables(home)]
    if registry and registry.get("codex_native"):
        config_parts.append(render_native_agent_tables(agent_tomls, registry))
    config_parts.append(render_mcp_toml(mcp, eff_allow, bridge=set(overlay)))
    out = {
        "AGENTS.md": render_agents_md(core, layer),
        "config.toml#managed": "\n\n".join(part for part in config_parts if part).strip(),
        "hooks.json": json.dumps(render_hooks_json(home), ensure_ascii=False, indent=2) + "\n",
    }
    for fname, toml_text in agent_tomls.items():
        out[f"agents/{fname}"] = toml_text
    out.update(render_profiles(home))
    return out

def collect_inputs(home: Path, context=None) -> dict:
    """Диагностический provenance: sha256 входов канона, не классификатор drift.
    MCP-срез включает только whitelisted-серверы, чтобы посторонние правки не создавали шум."""
    claude = home / ".claude"
    context = context or _load_sync_context(home)
    core, layer, wl_text, mcp, allow = _read_canon(home)
    sm_text = context["skills_manifest_text"]
    overlay = load_overlay(home)
    eff = effective_allow(allow, overlay)
    inputs = {
        "core/AGENTS.core.md": _sha(core),
        "codex-layer/AGENTS.codex.md": _sha(layer),
        "codex-layer/mcp-whitelist.json": _sha(wl_text),
        "codex-layer/skills-manifest.json": _sha(sm_text),
        ".claude.json#mcpServers": _sha(json.dumps(
            {k: mcp[k] for k in eff if k in mcp}, sort_keys=True, ensure_ascii=False)),
        "codex-mcp-overlay": _sha(json.dumps(sorted(overlay), ensure_ascii=False)),
    }
    for name in ("capability-registry.json", "capability-registry.schema.json"):
        p = claude / "codex-layer" / name
        if p.exists():
            inputs[f"codex-layer/{name}"] = _sha(p.read_text(encoding="utf-8"))
    native_instructions = claude / "codex-layer" / "agent-instructions"
    if native_instructions.exists():
        for f in sorted(native_instructions.glob("*.md")):
            inputs[f"codex-layer/agent-instructions/{f.name}"] = _sha(f.read_text(encoding="utf-8"))
    for f in sorted((claude / "agents").glob("*.md")):
        inputs[f"agents/{f.name}"] = _sha(f.read_text(encoding="utf-8"))
    tj = claude / "codex-layer" / "targets.json"
    if tj.exists():
        inputs["codex-layer/targets.json"] = _sha(tj.read_text(encoding="utf-8"))
    bt = claude / "codex-layer" / "base.toml"
    if bt.exists():
        inputs["codex-layer/base.toml"] = _sha(bt.read_text(encoding="utf-8"))
    prof = claude / "codex-layer" / "profiles"
    if prof.exists():
        for f in sorted(prof.glob("*.toml")):
            inputs[f"codex-layer/profiles/{f.name}"] = _sha(f.read_text(encoding="utf-8"))
    return inputs

def manifest_path(home: Path) -> Path:
    return home / ".claude" / ".local-state" / "codex-sync-manifest.json"

def save_manifest(home: Path, inputs: dict, outputs: dict) -> None:
    p = manifest_path(home)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"schema": 1, "inputs": inputs, "outputs": outputs},
                            ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")

def load_manifest(home: Path):
    p = manifest_path(home)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None    # битый манифест = отсутствующий (безопасный режим: дрейф не перезапишем)

def effective_allow(allow: list, overlay: list) -> list:
    """Единый список MCP для рендера и provenance без дублей."""
    return sorted(set(allow) | set(overlay))


def load_overlay(home: Path) -> list:
    """Оверлей доменного моста. Битый файл → warn + [] (fail-safe: SessionStart-хук
    не должен падать; render без моста → check покажет canon-newer/drift, не молчание)."""
    p = overlay_path(home)
    if not p.exists():
        return []
    try:
        return load_overlay_names(home)
    except OverlayError as e:
        print(f"[codex_sync] warn: оверлей {p} битый ({e}) — мост считается выключенным", file=sys.stderr)
        return []

def save_overlay(home: Path, names: list) -> None:
    p = overlay_path(home)
    normalized = normalize_overlay_names(names)
    if not normalized:
        p.unlink(missing_ok=True)
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    _write_atomic(p, json.dumps({"enable": normalized}, ensure_ascii=False, indent=2) + "\n")

def _output_path_codex(home: Path, key: str) -> Path:
    """Путь артефакта таргета codex на диске по ключу рендера."""
    codex = home / ".codex"
    if key == "config.toml#managed":
        return codex / "config.toml"
    if key.startswith("agents/"):
        return codex / "agents" / key.split("/", 1)[1]
    return codex / key          # AGENTS.md, hooks.json

# Реестр таргетов: имя среды → рендер артефактов и резолвер путей.
# Новая среда = новая пара функций + строка здесь; ядро (check/sync/manifest) не трогается.
TARGETS = {
    "codex": {"render": render_target_codex, "render_context": render_target_codex,
              "path": _output_path_codex},
}

def _enabled_targets(home: Path) -> list:
    p = home / ".claude" / "codex-layer" / "targets.json"
    if not p.exists():
        return ["codex"]                       # обратная совместимость со старым каноном
    names = json.loads(p.read_text(encoding="utf-8"))["enable"]
    unknown = [n for n in names if n not in TARGETS]
    if unknown:
        raise ValueError(f"targets.json: неизвестные таргеты {unknown}; доступны {sorted(TARGETS)}")
    return names

def render_all(home: Path, context=None) -> dict:
    """Объединённый рендер включённых таргетов. Ключи уникальны между таргетами."""
    out = {}
    for name in _enabled_targets(home):
        target = TARGETS[name]
        renderer = target.get("render_context") if context is not None else None
        part = renderer(home, context=context) if renderer else target["render"](home)
        dup = sorted(set(part) & set(out))
        if dup:
            raise ValueError(f"коллизия ключей между таргетами: {dup}")
        out.update(part)
    return out

def _output_path(home: Path, key: str) -> Path:
    for name in _enabled_targets(home):
        p = TARGETS[name]["path"](home, key)
        if p is not None:
            return p
    raise KeyError(key)

def read_disk_output(home: Path, key: str):
    p = _output_path(home, key)
    if not p.exists():
        return None
    if key == "config.toml#managed":
        m = re.search(re.escape(BEGIN) + r"\n(.*?)\n?" + re.escape(END), p.read_text(encoding="utf-8"), re.S)
        return m.group(1).rstrip() if m else None
    return p.read_text(encoding="utf-8")

def check(home: Path, expected=None, context=None) -> dict:
    """Трёхсторонняя сверка канон ↔ манифест ↔ диск. Категория на каждый ключ рендера."""
    res = {"clean": [], "canon-newer": [], "manual-drift": []}
    if not (home / ".codex").exists():
        return res
    context = context or _load_sync_context(home)
    expected = expected if expected is not None else render_all(home, context=context)
    man = load_manifest(home) or {}
    base_outputs = man.get("outputs", {})
    for key in sorted(expected):
        disk = read_disk_output(home, key)
        if disk is not None and disk == expected[key]:
            res["clean"].append(key)          # диск совпал с ожиданием — чисто в любом случае
        elif key == "config.toml#managed" and disk is not None and _split_codex_runtime_tables(disk)[0].rstrip() == expected[key]:
            # App мог вписать собственные доверенные хеши внутрь старого managed-блока.
            # Это безопасная миграция: sync вынесет их за маркер, не затирая значения.
            res["canon-newer"].append(key)
        elif disk is None or base_outputs.get(key) == _sha(disk):
            res["canon-newer"].append(key)    # диск = то, что синк писал в прошлый раз → безопасно перегенерить
        else:
            res["manual-drift"].append(key)   # диск отличается и от ожидания, и от последней записи синка
    # junctions скиллов сверяются по факту существования на диске (не по манифесту синка) —
    # снятый вручную junction иначе невидим для check() между запусками sync
    claude = home / ".claude"
    sm_path = claude / "codex-layer" / "skills-manifest.json"
    if sm_path.exists():
        manifest = context["skills_manifest"]
        skills_dir = claude / "skills"
        validate_skills_manifest(manifest, skills_dir)
        agents_skills_dir = home / ".agents" / "skills"
        for name in manifest.get("enable", []):
            source = skills_dir / name
            dst = agents_skills_dir / name
            if not (source / "SKILL.md").exists():
                continue
            if not dst.exists():
                res["canon-newer"].append(f"skills/{name}#junction")
            elif not _junction_points_to(dst, source):
                res["manual-drift"].append(f"skills/{name}#junction")
    return res

def _backup_once(p: Path) -> None:
    """[I3] Бэкап файла перед перезаписью — однократно (не затирает более старую копию)."""
    bak = p.with_suffix(p.suffix + ".bak-codex-sync")
    if p.exists() and not bak.exists():
        bak.write_bytes(p.read_bytes())

def _write_atomic(p: Path, text: str) -> None:
    """Атомарная запись: tmp-файл рядом + os.replace (без «половинчатого» файла при сбое)."""
    import os
    tmp = p.with_name(p.name + ".tmp-codex-sync")
    try:
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, p)
    finally:
        tmp.unlink(missing_ok=True)

def whitelist_path(home: Path) -> Path:
    """Переносимый whitelist MCP (решение Codex, хаб-задачи 2026-08-27):
    Codex читает свою копию ~/.codex/base/mcp-whitelist.json и не зависит от
    Claude-базы; канон остаётся в codex-layer, sync зеркалит его сюда."""
    local = home / ".codex" / "base" / "mcp-whitelist.json"
    return local if local.exists() else home / ".claude" / "codex-layer" / "mcp-whitelist.json"


def mirror_whitelist(home: Path) -> None:
    canon = home / ".claude" / "codex-layer" / "mcp-whitelist.json"
    if not canon.exists():
        return
    target = home / ".codex" / "base" / "mcp-whitelist.json"
    text = canon.read_text(encoding="utf-8")
    if not target.exists() or target.read_text(encoding="utf-8") != text:
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_atomic(target, text)
        print("[codex_sync] mcp-whitelist: зеркало обновлено -> ~/.codex/base/")


def ensure_feature_flags(home: Path) -> bool:
    """Вписывает обязательные ключи из codex-layer/feature-flags.json в
    СУЩЕСТВУЮЩУЮ таблицу [features] ~/.codex/config.toml (вторая таблица
    запрещена TOML). Только отсутствующие ключи: явное значение пользователя
    не перетирается. Возвращает True, если файл менялся."""
    flags_path = home / ".claude" / "codex-layer" / "feature-flags.json"
    cfg = home / ".codex" / "config.toml"
    if not flags_path.exists() or not cfg.exists():
        return False
    try:
        flags = json.loads(flags_path.read_text(encoding="utf-8")).get("features", {})
    except ValueError:
        print("[codex_sync] warn: feature-flags.json невалиден — пропущен", file=sys.stderr)
        return False
    if not flags:
        return False

    def fmt(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return str(v)
        return '"' + str(v) + '"'

    lines = cfg.read_text(encoding="utf-8").splitlines(keepends=True)
    start = next((i for i, ln in enumerate(lines)
                  if re.match(r"\s*\[features\]\s*$", ln)), None)
    if start is None:
        add = ["\n[features]\n"] + [f"{k} = {fmt(v)}\n" for k, v in flags.items()]
        new_lines = lines + add
    else:
        end = next((j for j in range(start + 1, len(lines))
                    if re.match(r"\s*\[", lines[j])), len(lines))
        present = set()
        for j in range(start + 1, end):
            m = re.match(r"\s*([A-Za-z0-9_.-]+)\s*=", lines[j])
            if m:
                present.add(m.group(1))
        add = [f"{k} = {fmt(v)}\n" for k, v in flags.items() if k not in present]
        if not add:
            return False
        new_lines = lines[:start + 1] + add + lines[start + 1:]
    new_text = "".join(new_lines)
    try:
        tomllib.loads(new_text)
    except tomllib.TOMLDecodeError as e:
        print(f"[codex_sync] error: feature-flags сделали config.toml невалидным — не записано: {e}",
              file=sys.stderr)
        return False
    _write_atomic(cfg, new_text)
    print(f"[codex_sync] feature-flags: добавлено {len(add)} ключ(а) в [features]")
    return True


def sync(home: Path, force=None, dry_run: bool = False) -> int:
    """Drift-aware сборка ~/.codex из канона ~/.claude.

    `dry_run` ничего не пишет. `force` разрешает выбранные drift-ключи или `all`.
    Возврат: 0 — полный успех; 3 — ручной drift частично пропущен; 4 — build-error
    имеет приоритет над drift и сохраняет прежний файл/manifest hash проблемного ключа.
    """
    force = set(force or ())
    claude, codex = home / ".claude", home / ".codex"
    if not codex.exists():
        print("[codex_sync] ~/.codex отсутствует — синк пропущен")
        return 0
    context = _load_sync_context(home)
    rendered = render_all(home, context=context)
    st = check(home, expected=rendered, context=context)
    forced = set(rendered) if "all" in force else force
    to_write = [k for k in sorted(rendered)
                if k in st["canon-newer"] or (k in st["manual-drift"] and k in forced)]
    skipped = [k for k in st["manual-drift"] if k not in forced]
    manifest = context["skills_manifest"]
    enabled_skills = [n for n in manifest.get("enable", []) if (claude / "skills" / n / "SKILL.md").exists()]
    if dry_run:
        print(f"AGENTS.md: {len(rendered['AGENTS.md'].encode('utf-8'))} байт; "
              f"писать: {len(to_write)}; дрейф-скип: {len(skipped)}; junctions: {len(enabled_skills)}")
        return 3 if skipped else 0
    build_error = False
    for key in to_write:
        p = _output_path(home, key)
        p.parent.mkdir(parents=True, exist_ok=True)
        _backup_once(p)
        if key == "config.toml#managed":
            existing = p.read_text(encoding="utf-8") if p.exists() else ""
            new_cfg = apply_managed_block(existing, rendered[key])
            try:
                tomllib.loads(new_cfg)
            except tomllib.TOMLDecodeError as e:
                print(f"[codex_sync] error: итоговый config.toml невалиден — запись отменена: {e}",
                      file=sys.stderr)
                build_error = True
                continue
            _write_atomic(p, new_cfg)
        else:
            _write_atomic(p, rendered[key])
    ensure_skill_junctions(manifest, claude / "skills", home / ".agents" / "skills")
    ensure_feature_flags(home)
    mirror_whitelist(home)
    # манифест: записанное/чистое = ожидаемый хеш; пропущенный дрейф (ручной или гейт-ошибка) = прежнее значение
    old = (load_manifest(home) or {}).get("outputs", {})
    unwritten = set(skipped) | ({"config.toml#managed"} if build_error else set())
    outputs = {k: (_sha(rendered[k]) if k not in unwritten else old.get(k, ""))
               for k in rendered}
    save_manifest(home, collect_inputs(home, context=context), outputs)
    for k in skipped:
        print(f"[codex_sync] manual-drift пропущен: {k} (занеси в канон или sync --force-overwrite {k})")
    return 4 if build_error else (3 if skipped else 0)

def diff_cmd(home: Path) -> int:
    """Unified diff всех manual-drift ключей: ожидание из канона vs факт на диске. Всегда 0."""
    import difflib
    context = _load_sync_context(home)
    expected = render_all(home, context=context)
    st = check(home, expected=expected, context=context)
    for key in st["manual-drift"]:
        if key not in expected:
            print(f"manual-drift: {key} — локальный каталог не является junction на канон")
            continue
        disk = read_disk_output(home, key) or ""
        for line in difflib.unified_diff(expected[key].splitlines(), disk.splitlines(),
                                         fromfile=f"{key} (ожидаемо из канона)",
                                         tofile=f"{key} (факт на диске)", lineterm=""):
            print(line)
        print()
    return 0

def mcp_cmd(home: Path, action: str, names: list) -> int:
    """Доменный MCP-мост по требованию: on = патч CRLF + оверлей + sync;
    off = снять оверлей + sync; status = whitelist/оверлей/патч-статус."""
    import mcp_crlf_patch as patcher
    if action not in ("on", "off", "status"):
        print(f"[codex_sync] error: неизвестное действие {action} (on|off|status)", file=sys.stderr)
        return 1
    if not isinstance(names, list) or not all(isinstance(name, str) and name.strip() for name in names):
        print("[codex_sync] error: имена серверов должны быть непустыми строками", file=sys.stderr)
        return 1
    names = sorted(set(names))
    mcp = json.loads((home / ".claude.json").read_text(encoding="utf-8")).get("mcpServers", {})
    overlay = load_overlay(home)
    if action == "status":
        if names:
            print("[codex_sync] error: mcp status не принимает имена серверов", file=sys.stderr)
            return 1
        allow = json.loads(whitelist_path(home).read_text(encoding="utf-8"))["allow"]
        print(f"whitelist: {', '.join(sorted(allow))}")
        print(f"мост: {', '.join(overlay) if overlay else '(выключен)'}")
        for n in overlay:
            venv = patcher.venv_from_command(mcp.get(n, {}).get("command", ""))
            st = patcher.process_venv(venv, check_only=True) if venv else "не python-venv"
            print(f"  {n}: патч {st}")
        return 0
    if action == "on":
        if not names:
            print("[codex_sync] error: укажи сервер: mcp on <имя> [...]", file=sys.stderr)
            return 1
        unknown = [n for n in names if n not in mcp]
        if unknown:
            print(f"[codex_sync] error: нет в ~/.claude.json: {', '.join(unknown)}; "
                  f"доступны: {', '.join(sorted(mcp))}", file=sys.stderr)
            return 1
        for n in names:                       # патч ДО включения; провал → конфиг не тронут
            venv = patcher.venv_from_command(mcp[n].get("command", ""))
            if venv is None:
                print(f"[codex_sync] {n}: не python-venv — CRLF-патч не требуется")
                continue
            st = patcher.process_venv(venv, check_only=False)
            print(f"[codex_sync] {n}: патч {st}")
            if st not in patcher.OK:
                print(f"[codex_sync] error: {n}: патч не применён ({st}) — "
                      f"мост не включён, конфиг не тронут", file=sys.stderr)
                return 1
        save_overlay(home, sorted(set(overlay) | set(names)))
        rc = sync(home)
        print(f"[codex_sync] мост включён: {', '.join(load_overlay(home))} — рестартни Codex")
        return rc
    # off: без имён = выключить всё
    inactive = [name for name in names if name not in overlay]
    if inactive:
        print(f"[codex_sync] error: не включены в мост: {', '.join(inactive)}", file=sys.stderr)
        return 1
    remove = set(names) if names else set(overlay)
    save_overlay(home, [n for n in overlay if n not in remove])
    rc = sync(home)
    print("[codex_sync] мост выключен — рестартни Codex")
    return rc

def main(argv=None, home: Path | None = None) -> int:
    """Разобрать CLI и вернуть код завершения без неявного завершения процесса."""
    import argparse
    ap = argparse.ArgumentParser(description="Синк канона ~/.claude в ~/.codex")
    ap.add_argument("cmd", nargs="?", default="sync", choices=["sync", "check", "diff", "mcp"])
    ap.add_argument("rest", nargs="*", metavar="on|off|status [имя ...]",
                    help="для mcp: действие и имена серверов")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force-overwrite", action="append", default=[], metavar="KEY|all",
                     help="перезаписать ключ (или all) поверх ручного дрейфа")
    args = ap.parse_args(argv)
    home = home or Path.home()
    if args.cmd != "mcp" and args.rest:
        print("[codex_sync] error: аргументы допустимы только с mcp", file=sys.stderr)
        return 2
    if args.cmd != "sync" and (args.dry_run or args.force_overwrite):
        print("[codex_sync] error: --dry-run и --force-overwrite допустимы только с sync", file=sys.stderr)
        return 2
    if args.cmd == "check":
        res = check(home)
        for cat in ("canon-newer", "manual-drift"):
            for key in res[cat]:
                print(f"{cat}\t{key}")
        return 3 if res["manual-drift"] else (2 if res["canon-newer"] else 0)
    elif args.cmd == "diff":
        return diff_cmd(home)
    elif args.cmd == "mcp":
        action = args.rest[0] if args.rest else "status"
        return mcp_cmd(home, action, args.rest[1:])
    else:
        return sync(home, force=set(args.force_overwrite), dry_run=args.dry_run)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")   # кириллица при захвате из PowerShell
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    sys.exit(main())
