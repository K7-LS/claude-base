# -*- coding: utf-8 -*-
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))
from codex_sync import apply_managed_block, BEGIN, END


def test_cli_docstring_lists_current_commands_and_force_option():
    import codex_sync
    assert "sync|check|diff|mcp" in codex_sync.__doc__
    assert "--force-overwrite" in codex_sync.__doc__

def test_sync_docstring_describes_full_return_and_option_contract():
    from codex_sync import sync
    assert "0" in sync.__doc__ and "3" in sync.__doc__ and "4" in sync.__doc__
    assert "dry_run" in sync.__doc__ and "force" in sync.__doc__

def test_autosync_log_append_is_explicit_utf8():
    script = (pathlib.Path(__file__).parents[1] / "codex-autosync.ps1").read_text(encoding="utf-8")
    assert "Add-Content -LiteralPath $logFile -Encoding UTF8" in script

def test_block_appended_preserves_foreign_content():
    src = 'model = "gpt-5.6-sol"\n\n[plugins."visualize@openai-bundled"]\nenabled = true\n'
    out = apply_managed_block(src, "[mcp_servers.time]\ncommand = 'uvx'\n")
    assert src.rstrip("\n") in out          # чужое сохранено байт-в-байт
    assert BEGIN in out and END in out
    assert "[mcp_servers.time]" in out

def test_idempotent_and_replaces_old_block():
    src = "x = 1\n"
    once = apply_managed_block(src, "a = 1\n")
    twice = apply_managed_block(once, "a = 1\n")
    assert once == twice                     # идемпотентность
    updated = apply_managed_block(once, "a = 2\n")
    assert "a = 2" in updated and "a = 1" not in updated

def test_backslash_payload_survives_reapply():
    payload = "command = 'C:\\Users\\Daniil\\.claude\\x.exe'\nref = 'a\\1b'\n"
    once = apply_managed_block("x = 1\n", payload)
    twice = apply_managed_block(once, payload)   # раньше падало re.error
    assert once == twice
    assert "C:\\Users\\Daniil" in twice

def test_two_blocks_consolidated_to_one():
    src = f"a = 1\n{BEGIN}\nold1\n{END}\nb = 2\n{BEGIN}\nold2\n{END}\n"
    out = apply_managed_block(src, "new\n")
    assert out.count(BEGIN) == 1 and out.count(END) == 1
    assert "a = 1" in out and "b = 2" in out      # чужое между блоками сохранено
    assert "old1" not in out and "old2" not in out

def test_empty_file():
    assert apply_managed_block("", "a = 1\n").startswith(BEGIN)

def test_render_mcp_toml_whitelist_and_env():
    from codex_sync import render_mcp_toml
    servers = {
        "time": {"command": "uvx", "args": ["mcp-server-time"]},
        "excel": {"command": "uvx", "args": ["excel-mcp-server"], "env": {"X": "a\\b"}},
    }
    out = render_mcp_toml(servers, allow=["excel"])
    assert "[mcp_servers.excel]" in out
    assert "mcp_servers.time" not in out            # вне белого списка
    assert "args = ['excel-mcp-server']" in out
    assert "[mcp_servers.excel.env]" in out and "X = 'a\\b'" in out

def test_t_values_parse_as_real_toml():
    import tomllib
    from codex_sync import render_mcp_toml
    servers = {
        "s1": {"command": "run", "args": ["it's arg", "line1\nline2", "C:\\x\\y"]},
    }
    out = render_mcp_toml(servers, allow=["s1"])
    parsed = tomllib.loads(out)
    assert parsed["mcp_servers"]["s1"]["args"] == ["it's arg", "line1\nline2", "C:\\x\\y"]

def test_render_skills_toml(tmp_path):
    (tmp_path / "excel-helper").mkdir()
    (tmp_path / "excel-helper" / "SKILL.md").write_text("---\nname: excel-helper\n---\n", encoding="utf-8")
    from codex_sync import render_skills_toml
    manifest = {"enable": ["excel-helper", "ghost-skill"]}
    out = render_skills_toml(manifest, tmp_path)
    assert out.count("[[skills.config]]") == 1      # ghost-skill пропущен
    assert "excel-helper" in out and "enabled = true" in out

def test_render_hooks_json_structure(tmp_path):
    # Канон hooks заменён ОСОЗНАННО решением Codex (приёмка 2026-08-28):
    # one-way уведомление о релизе + журнал моста; auto-pull/push и
    # session-хуки не возвращаются (противоречат one-way контуру sync-base).
    from codex_sync import render_hooks_json
    hooks = render_hooks_json(tmp_path)
    assert hooks["description"] == "One-way Codex base release notification."
    # Память проекта возвращена решением владельца 2026-09-01; auto-pull/push
    # и context governor по-прежнему не возвращаются.
    assert set(hooks["hooks"].keys()) == {"SessionStart", "Stop", "PostToolUse"}

    start = hooks["hooks"]["SessionStart"][0]
    assert start["matcher"] == "^startup$"
    release, memory = start["hooks"]
    assert "project-memory-hooks" in memory["command"]
    assert memory["command"].endswith('session_start.ps1"')
    assert memory["timeout"] == 10
    (stop,) = hooks["hooks"]["Stop"][0]["hooks"]
    assert stop["command"].endswith('session_end.ps1"') and stop["timeout"] == 20
    import json as _json
    for banned in ("auto-pull", "auto-push", "codex_context_governor"):
        assert banned not in _json.dumps(hooks, ensure_ascii=False)
    assert "check_release.ps1" in release["command"]
    assert "check_release.ps1" in release["commandWindows"]
    assert release["timeout"] == 38
    assert str(tmp_path) not in release["command"]        # без хардкода профиля

    ptu = hooks["hooks"]["PostToolUse"][0]
    assert ptu["matcher"] == "^(mcp__)?claude(/|__)"
    (journal,) = ptu["hooks"]
    assert "interop_journal.py" in journal["command"]
    assert journal["command"] == journal["commandWindows"]
    assert str(tmp_path) in journal["command"]            # путь журнала — от home
    assert journal["command"].endswith("--source codex")
    assert journal["timeout"] == 15

    for group in hooks["hooks"].values():
        for m in group:
            for h in m["hooks"]:
                assert h["type"] == "command"

    import json
    json.loads(json.dumps(hooks, ensure_ascii=False))             # сериализуемость round-trip

def test_convert_agent_md():
    from codex_sync import convert_agent_md
    text = (pathlib.Path(__file__).parent / "fixtures" / "agent_sample.md").read_text(encoding="utf-8")
    fname, toml_text = convert_agent_md(text)
    assert fname == "sample-auditor.toml"
    assert "model = 'gpt-5.6-terra'" in toml_text            # sonnet → terra
    assert "mcp__excel__" not in toml_text                    # инструменты заменены
    assert "spreadsheets" in toml_text
    assert "name = 'sample-auditor'" in toml_text
    import tomllib
    assert tomllib.loads(toml_text)["description"] == "Тестовый ревьюер"

def test_convert_agent_md_crlf_and_block_description():
    from codex_sync import convert_agent_md
    import tomllib
    md = ("---\r\nname: crlf-agent\r\ndescription: |\r\n  Первая строка.\r\n  Вторая строка (Ф\\.\\d{4}).\r\nmodel: haiku\r\n---\r\n"
          "Тело с путём C:\\Users\\x и регекспом \\{\\{placeholder\\}\\}.\r\n")
    fname, toml_text = convert_agent_md(md)
    parsed = tomllib.loads(toml_text)
    assert fname == "crlf-agent.toml"
    assert parsed["model"] == "gpt-5.6-luna"
    assert "Вторая строка" in parsed["description"] and parsed["description"].strip() != "|"
    assert "C:\\Users\\x" in parsed["developer_instructions"]

def test_convert_agent_md_triple_quote_fallback():
    from codex_sync import convert_agent_md
    import tomllib
    md = "---\nname: tq\ndescription: d\nmodel: sonnet\n---\ncode: '''docstring''' и \\ бэкслэш\n"
    _, toml_text = convert_agent_md(md)
    parsed = tomllib.loads(toml_text)
    assert "'''docstring'''" in parsed["developer_instructions"]
    assert "\\ бэкслэш" in parsed["developer_instructions"]

def test_convert_agent_md_wildcard_tools():
    from codex_sync import convert_agent_md
    text = ("---\nname: w\ndescription: d\nmodel: haiku\n---\n"
            "Инструменты: mcp__excel__* и mcp__word__\\* и mcp__pdf-mcp__*.\n")
    _, toml_text = convert_agent_md(text)
    assert "mcp__" not in toml_text
    assert "spreadsheets" in toml_text and "documents" in toml_text

def test_convert_agent_registry_neutralizes_legacy_tool_prose():
    from codex_sync import convert_agent_md
    registry = {
        "tool_map": [],
        "_capabilities": {},
        "_roles": {
            "legacy-prose": {
                "required_capabilities": [], "optional_capabilities": [], "permission_class": "rw",
                "input_contract": "in", "output_contract": "out",
                "verification": {"claude": "static", "codex": "static"},
                "fallback": "none", "handoff": "none",
            }
        },
    }
    md = ("---\nname: legacy-prose\ndescription: exa\nmodel: haiku\n---\n"
          "exa → firecrawl → fetch → playwright → WebFetch; AskUserQuestion; Bash, Glob, Grep; `tail`; `grep`.\n")
    _, toml_text = convert_agent_md(md, registry)
    for legacy in ("exa", "firecrawl", "playwright", "WebFetch", "AskUserQuestion", "Bash", "Glob", "Grep", "`tail`", "`grep`"):
        assert legacy.lower() not in toml_text.lower()
    assert "capability `web.search`" in toml_text
    assert "уточняющий вопрос пользователю" in toml_text

def test_convert_agent_readonly_sandbox():
    from codex_sync import convert_agent_md
    ro = "---\nname: r\ndescription: d\nmodel: sonnet\ntools: Read, Grep, mcp__excel__read_data_from_excel\n---\nТело.\n"
    _, t = convert_agent_md(ro)
    assert 'sandbox_mode = "read-only"' in t
    rw = "---\nname: w\ndescription: d\nmodel: sonnet\ntools: Read, Write, Edit\n---\nТело.\n"
    _, t2 = convert_agent_md(rw)
    assert "sandbox_mode" not in t2

def test_render_agents_md_limit():
    from codex_sync import render_agents_md
    out = render_agents_md("ядро", "слой")
    assert out.startswith("Отвечай пользователю по-русски")
    assert "ядро" in out and "слой" in out
    import pytest
    with pytest.raises(ValueError):
        render_agents_md("x" * 33000, "y")

def test_agents_md_written_lf(tmp_path, monkeypatch):
    # мини-проверка: render_agents_md не содержит \r, а гейт меряет то, что пишется
    from codex_sync import render_agents_md
    out = render_agents_md("ядро", "слой")
    assert "\r" not in out

def test_render_mcp_toml_http_server():
    from codex_sync import render_mcp_toml
    servers = {"exa": {"type": "http", "url": "https://mcp.exa.ai/mcp"},
               "bad": {"type": "http"}}
    out = render_mcp_toml(servers, allow=["exa", "bad"])
    assert "[mcp_servers.exa]" in out and "url = 'https://mcp.exa.ai/mcp'" in out
    assert "command" not in out.split("[mcp_servers.exa]")[1].split("[")[0]
    assert "mcp_servers.bad" not in out

def test_collect_agent_tomls_skips_nameless(tmp_path):
    from codex_sync import collect_agent_tomls
    (tmp_path / "good.md").write_text("---\nname: good\ndescription: d\nmodel: haiku\n---\nТело.\n", encoding="utf-8")
    (tmp_path / "agents.md").write_text("# Индекс агентов\nпросто текст без фронтматтером\n", encoding="utf-8")
    result = collect_agent_tomls(tmp_path)
    assert list(result) == ["good.toml"]

def test_ensure_skill_junctions(tmp_path):
    from codex_sync import ensure_skill_junctions
    src = tmp_path / "claude_skills"; dst = tmp_path / "agents_skills"
    (src / "excel-helper").mkdir(parents=True)
    (src / "excel-helper" / "SKILL.md").write_text("---\nname: excel-helper\n---\n", encoding="utf-8")
    (src / "old-skill").mkdir()
    (src / "old-skill" / "SKILL.md").write_text("---\nname: old-skill\n---\n", encoding="utf-8")
    manifest = {"enable": ["excel-helper", "ghost"]}
    made = ensure_skill_junctions(manifest, src, dst)
    assert (dst / "excel-helper" / "SKILL.md").exists()      # junction работает
    assert made == ["excel-helper"]                           # ghost пропущен с warn
    # идемпотентность
    assert ensure_skill_junctions(manifest, src, dst) == []
    # cleanup: скилл выпал из манифеста -> junction снимается
    import subprocess
    subprocess.run(["cmd", "/c", "mklink", "/J", str(dst / "old-skill"), str(src / "old-skill")], capture_output=True)
    ensure_skill_junctions(manifest, src, dst)
    assert not (dst / "old-skill").exists()
    assert (src / "old-skill" / "SKILL.md").exists()          # источник цел

def test_skills_manifest_requires_explicit_enable_or_skip(tmp_path):
    import pytest
    from codex_sync import validate_skills_manifest
    skills = tmp_path / "skills"
    for name in ("enabled", "skipped"):
        (skills / name).mkdir(parents=True)
        (skills / name / "SKILL.md").write_text(f"---\nname: {name}\n---\n", encoding="utf-8")
    validate_skills_manifest(
        {"enable": ["enabled"], "skip_reason": {"skipped": "нужен adapter"}}, skills
    )
    with pytest.raises(ValueError, match="не классифицированы"):
        validate_skills_manifest({"enable": ["enabled"], "skip_reason": {}}, skills)
    with pytest.raises(ValueError, match="одновременно"):
        validate_skills_manifest(
            {"enable": ["enabled"], "skip_reason": {"enabled": "дубль", "skipped": "причина"}},
            skills,
        )

def test_render_all_keys_and_purity(make_canon):
    from codex_sync import render_all
    home = make_canon()
    out = render_all(home)
    assert set(out) == {"AGENTS.md", "config.toml#managed", "hooks.json", "agents/тест-агент.toml",
                        "plus.config.toml", "pro.config.toml"}
    assert "[mcp_servers.time]" in out["config.toml#managed"]
    assert "excel" not in out["config.toml#managed"]          # whitelist работает
    assert out["config.toml#managed"] == out["config.toml#managed"].rstrip()
    # чистота: на диск ничего не записано
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == "x = 1\n"
    assert not (home / ".codex" / "AGENTS.md").exists()

def test_collect_inputs_tracks_canon_and_mcp_slice(make_canon):
    from codex_sync import collect_inputs
    home = make_canon()
    h1 = collect_inputs(home)
    assert "core/AGENTS.core.md" in h1 and "agents/тест-агент.md" in h1
    assert ".claude.json#mcpServers" in h1
    # правка канона меняет хеш
    (home / ".claude" / "core" / "AGENTS.core.md").write_text("# Ядро v2\n", encoding="utf-8")
    h2 = collect_inputs(home)
    assert h1["core/AGENTS.core.md"] != h2["core/AGENTS.core.md"]
    # правка НЕ-whitelisted сервера в .claude.json срез не трогает
    import json
    cj = home / ".claude.json"
    data = json.loads(cj.read_text(encoding="utf-8"))
    data["mcpServers"]["excel"]["args"] = ["other"]
    cj.write_text(json.dumps(data), encoding="utf-8")
    h3 = collect_inputs(home)
    assert h2[".claude.json#mcpServers"] == h3[".claude.json#mcpServers"]

def _seed_manifest(home):
    """Синк-состояние 'всё чисто': диск = ожидаемое, манифест записан."""
    from codex_sync import render_all, collect_inputs, save_manifest, _sha, apply_managed_block
    rendered = render_all(home)
    codex = home / ".codex"
    (codex / "AGENTS.md").write_text(rendered["AGENTS.md"], encoding="utf-8", newline="\n")
    cfg = codex / "config.toml"
    cfg.write_text(apply_managed_block(cfg.read_text(encoding="utf-8"), rendered["config.toml#managed"]),
                   encoding="utf-8", newline="\n")
    (codex / "hooks.json").write_text(rendered["hooks.json"], encoding="utf-8", newline="\n")
    (codex / "agents").mkdir(exist_ok=True)
    for k in rendered:
        if k.startswith("agents/"):
            (codex / "agents" / k.split("/", 1)[1]).write_text(rendered[k], encoding="utf-8", newline="\n")
        elif k not in ("AGENTS.md", "config.toml#managed", "hooks.json"):
            (codex / k).write_text(rendered[k], encoding="utf-8", newline="\n")   # плоские выходы (профили и т.п.)
    save_manifest(home, collect_inputs(home), {k: _sha(v) for k, v in rendered.items()})

def test_check_clean(make_canon):
    from codex_sync import check
    home = make_canon(); _seed_manifest(home)
    res = check(home)
    assert res["canon-newer"] == [] and res["manual-drift"] == []
    assert "AGENTS.md" in res["clean"]

def test_check_canon_newer_after_core_edit(make_canon):
    from codex_sync import check
    home = make_canon(); _seed_manifest(home)
    (home / ".claude" / "core" / "AGENTS.core.md").write_text("# Ядро v2\n", encoding="utf-8")
    res = check(home)
    assert "AGENTS.md" in res["canon-newer"] and res["manual-drift"] == []

def test_check_manual_drift_after_disk_edit(make_canon):
    from codex_sync import check
    home = make_canon(); _seed_manifest(home)
    agents_md = home / ".codex" / "AGENTS.md"
    agents_md.write_text(agents_md.read_text(encoding="utf-8") + "\nручная правка\n",
                         encoding="utf-8", newline="\n")
    res = check(home)
    assert res["manual-drift"] == ["AGENTS.md"] and res["canon-newer"] == []

def test_check_both_categories_and_managed_block_extraction(make_canon):
    from codex_sync import check, read_disk_output
    home = make_canon(); _seed_manifest(home)
    # ручная правка ВНУТРИ managed-блока + правка канона
    cfg = home / ".codex" / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("[mcp_servers.time]", "[mcp_servers.time2]"),
                   encoding="utf-8", newline="\n")
    (home / ".claude" / "core" / "AGENTS.core.md").write_text("# Ядро v3\n", encoding="utf-8")
    res = check(home)
    assert "config.toml#managed" in res["manual-drift"]
    assert "AGENTS.md" in res["canon-newer"]
    assert "time2" in read_disk_output(home, "config.toml#managed")

def test_check_missing_codex_dir_is_quiet(make_canon, tmp_path):
    from codex_sync import check
    home = make_canon()
    import shutil; shutil.rmtree(home / ".codex")
    res = check(home)
    assert res == {"clean": [], "canon-newer": [], "manual-drift": []}

def test_sync_writes_manifest_and_regenerates_on_canon_change(make_canon):
    from codex_sync import sync, check, manifest_path
    home = make_canon()
    assert sync(home) == 0                                   # первый прогон: сборка + манифест
    assert manifest_path(home).exists()
    assert check(home)["manual-drift"] == [] and check(home)["canon-newer"] == []
    (home / ".claude" / "core" / "AGENTS.core.md").write_text("# Ядро v2\n", encoding="utf-8")
    assert sync(home) == 0                                   # canon-newer → перегенерено
    assert "Ядро v2" in (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")

def test_first_sync_preserves_preexisting_manual_drift(make_canon):
    from codex_sync import sync, check, manifest_path
    home = make_canon()
    agents_md = home / ".codex" / "AGENTS.md"
    agents_md.write_text("ручная правка до первого синка\n", encoding="utf-8", newline="\n")

    assert not manifest_path(home).exists()
    assert sync(home) == 3
    assert agents_md.read_text(encoding="utf-8") == "ручная правка до первого синка\n"
    assert check(home)["manual-drift"] == ["AGENTS.md"]

def test_sync_skips_manual_drift_and_returns_3(make_canon):
    from codex_sync import sync
    home = make_canon(); sync(home)
    agents_md = home / ".codex" / "AGENTS.md"
    agents_md.write_text("ручная правка\n", encoding="utf-8", newline="\n")
    (home / ".claude" / "core" / "AGENTS.core.md").write_text("# Ядро v2\n", encoding="utf-8")
    assert sync(home) == 3                                   # дрейф скипнут
    assert agents_md.read_text(encoding="utf-8") == "ручная правка\n"   # НЕ перезаписан
    assert "Ядро v2" not in agents_md.read_text(encoding="utf-8")

def test_sync_force_overwrite_resets_drift(make_canon):
    from codex_sync import sync, check
    home = make_canon(); sync(home)
    (home / ".codex" / "AGENTS.md").write_text("ручная правка\n", encoding="utf-8", newline="\n")
    assert sync(home, force={"all"}) == 0
    res = check(home)
    assert res["manual-drift"] == [] and res["canon-newer"] == []

def test_sync_force_overwrite_only_selected_drift(make_canon):
    from codex_sync import sync, check, render_all
    home = make_canon(); sync(home)
    agents_md = home / ".codex" / "AGENTS.md"
    hooks_json = home / ".codex" / "hooks.json"
    agents_md.write_text("ручная правка AGENTS\n", encoding="utf-8", newline="\n")
    hooks_json.write_text("ручная правка hooks\n", encoding="utf-8", newline="\n")

    assert sync(home, force={"AGENTS.md"}) == 3
    assert agents_md.read_text(encoding="utf-8") == render_all(home)["AGENTS.md"]
    assert hooks_json.read_text(encoding="utf-8") == "ручная правка hooks\n"
    assert check(home)["manual-drift"] == ["hooks.json"]

def test_diff_renders_once_and_emits_each_warning_once(make_canon, capsys):
    from codex_sync import diff_cmd, sync
    home = make_canon(); sync(home)
    capsys.readouterr()
    (home / ".claude" / "agents" / "agents.md").write_text(
        "нет frontmatter и имени\n", encoding="utf-8")

    assert diff_cmd(home) == 0

    assert capsys.readouterr().err.count("agents.md пропущен") == 1

def test_sync_reads_skills_manifest_once(make_canon, monkeypatch):
    from codex_sync import sync
    home = make_canon()
    manifest = home / ".claude" / "codex-layer" / "skills-manifest.json"
    original = pathlib.Path.read_text
    reads = 0

    def counted_read_text(path, *args, **kwargs):
        nonlocal reads
        if path == manifest:
            reads += 1
        return original(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", counted_read_text)
    assert sync(home) == 0
    assert reads == 1

def test_manifest_inputs_are_diagnostic_provenance(make_canon):
    from codex_sync import check, collect_inputs, load_manifest, sync
    assert "диагност" in collect_inputs.__doc__.lower()
    home = make_canon(); sync(home)
    before = load_manifest(home)
    (home / ".claude" / "core" / "AGENTS.core.md").write_text(
        "# Ядро\nПравило 1: думай, прежде чем действовать.\n\n",
        encoding="utf-8", newline="\n")

    # Изменение входных байтов, не меняющее render из-за strip(), остаётся
    # diagnostic provenance и не создаёт ложный output drift.
    assert check(home)["manual-drift"] == []
    assert check(home)["canon-newer"] == []
    assert load_manifest(home)["inputs"] == before["inputs"]

def test_write_atomic_cleans_tmp_when_replace_fails(tmp_path, monkeypatch):
    import os
    import pytest
    from codex_sync import _write_atomic

    target = tmp_path / "target.txt"
    target.write_text("исходное\n", encoding="utf-8")
    tmp = target.with_name(target.name + ".tmp-codex-sync")

    def fail_replace(source, destination):
        raise OSError("replace failed")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        _write_atomic(target, "новое\n")

    assert target.read_text(encoding="utf-8") == "исходное\n"
    assert not tmp.exists()

def test_sync_preserves_foreign_config_and_is_atomic_style(make_canon):
    from codex_sync import sync
    home = make_canon(); sync(home)
    cfg = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert cfg.startswith("x = 1")                            # чужое цело
    assert "[mcp_servers.time]" in cfg
    assert not list((home / ".codex").glob("*.tmp-codex-sync"))   # tmp-файлы подчистились

def test_sync_migrates_and_preserves_codex_runtime_state(make_canon):
    from codex_sync import BEGIN, END, check, sync
    home = make_canon(); sync(home)
    cfg = home / ".codex" / "config.toml"
    raw = cfg.read_text(encoding="utf-8")
    runtime = "[hooks.state]\n\n[memories]\ngenerate_memories = true\n"
    cfg.write_text(raw.replace("[mcp_servers.time]", runtime + "\n[mcp_servers.time]"), encoding="utf-8")
    assert "config.toml#managed" in check(home)["canon-newer"]
    assert sync(home) == 0
    migrated = cfg.read_text(encoding="utf-8")
    assert migrated.index(END) < migrated.index("[hooks.state]")
    assert "generate_memories = true" in migrated
    assert check(home)["manual-drift"] == [] and check(home)["canon-newer"] == []

def test_cua_repl_inside_managed_is_canon_newer_and_sync_relocates(make_canon):
    # Решение Codex (приёмка 2026-08-28): cua_repl — App-owned runtime table;
    # запись App внутрь managed-блока — canon-newer, sync выносит за маркер
    # без изменения значений, повторный sync идемпотентен.
    import tomllib
    from codex_sync import END, check, sync
    home = make_canon(); sync(home)
    cfg = home / ".codex" / "config.toml"
    raw = cfg.read_text(encoding="utf-8")
    section = ("[mcp_servers.cua_repl]\n"
               "command = 'C:\\WindowsApps\\OpenAI.Codex_26.825_x64\\ChatGPT.exe'\n"
               "enabled = false\n")
    cfg.write_text(raw.replace(END, section + END), encoding="utf-8")
    res = check(home)
    assert "config.toml#managed" in res["canon-newer"]
    assert "config.toml#managed" not in res["manual-drift"]
    assert sync(home) == 0
    migrated = cfg.read_text(encoding="utf-8")
    assert migrated.index(END) < migrated.index("[mcp_servers.cua_repl]")
    assert "enabled = false" in migrated and "ChatGPT.exe" in migrated
    tomllib.loads(migrated)
    assert sync(home) == 0                                    # идемпотентность
    again = cfg.read_text(encoding="utf-8")
    assert again.count("[mcp_servers.cua_repl]") == 1         # дубля нет
    assert check(home)["manual-drift"] == [] and check(home)["canon-newer"] == []

def test_cua_repl_version_bump_outside_managed_is_not_drift(make_canon):
    # Версионный WindowsApps-путь меняется при обновлении App — drift не создаётся.
    import tomllib
    from codex_sync import check, sync
    home = make_canon(); sync(home)
    cfg = home / ".codex" / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8") +
                   "\n[mcp_servers.cua_repl]\n"
                   "command = 'C:\\WindowsApps\\OpenAI.Codex_1_x64\\ChatGPT.exe'\n"
                   "enabled = false\n", encoding="utf-8")
    assert check(home)["manual-drift"] == []
    cfg.write_text(cfg.read_text(encoding="utf-8").replace("Codex_1_x64", "Codex_2_x64"),
                   encoding="utf-8")
    assert check(home)["manual-drift"] == []
    assert sync(home) == 0
    merged = cfg.read_text(encoding="utf-8")
    assert "Codex_2_x64" in merged                            # значение App не тронуто
    tomllib.loads(merged)

def test_cua_repl_duplicate_copies_collapse_deterministically(make_canon):
    # Две копии секции (внутри и снаружи managed) схлопываются детерминированно:
    # побеждает копия из managed-блока (самая свежая запись App).
    import tomllib
    from codex_sync import END, check, sync
    home = make_canon(); sync(home)
    cfg = home / ".codex" / "config.toml"
    raw = cfg.read_text(encoding="utf-8")
    inside = ("[mcp_servers.cua_repl]\n"
              "command = 'C:\\WindowsApps\\OpenAI.Codex_2_x64\\ChatGPT.exe'\n"
              "enabled = false\n")
    outside = ("\n[mcp_servers.cua_repl]\n"
               "command = 'C:\\WindowsApps\\OpenAI.Codex_1_x64\\ChatGPT.exe'\n"
               "enabled = false\n")
    cfg.write_text(raw.replace(END, inside + END) + outside, encoding="utf-8")
    assert sync(home) == 0
    merged = cfg.read_text(encoding="utf-8")
    assert merged.count("[mcp_servers.cua_repl]") == 1
    assert "Codex_2_x64" in merged and "Codex_1_x64" not in merged
    tomllib.loads(merged)
    assert check(home)["manual-drift"] == [] and check(home)["canon-newer"] == []

def test_check_reports_missing_skill_junction_and_sync_heals(make_canon):
    import json as _json
    from codex_sync import sync, check
    home = make_canon()
    claude = home / ".claude"
    skill = claude / "skills" / "тест-скилл"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: тест-скилл\n---\n", encoding="utf-8")
    (claude / "codex-layer" / "skills-manifest.json").write_text(
        _json.dumps({"enable": ["тест-скилл"]}), encoding="utf-8")
    assert sync(home) == 0                                    # junction создан
    j = home / ".agents" / "skills" / "тест-скилл"
    assert j.exists()
    import subprocess; subprocess.run(["cmd", "/c", "rmdir", str(j)], capture_output=True)  # junction снят
    res = check(home)
    assert "skills/тест-скилл#junction" in res["canon-newer"]
    assert sync(home) == 0                                    # sync вылечил
    assert j.exists() and check(home)["canon-newer"] == []

def test_foreign_skill_directory_is_manual_drift_and_preserved(make_canon):
    import json as _json
    from codex_sync import sync, check, _is_junction
    home = make_canon()
    claude = home / ".claude"
    skill = claude / "skills" / "тест-скилл"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: тест-скилл\n---\n", encoding="utf-8")
    (claude / "codex-layer" / "skills-manifest.json").write_text(
        _json.dumps({"enable": ["тест-скилл"], "skip_reason": {}}), encoding="utf-8")
    foreign = home / ".agents" / "skills" / "тест-скилл"
    foreign.mkdir(parents=True)
    (foreign / "LOCAL.txt").write_text("не удалять", encoding="utf-8")
    assert "skills/тест-скилл#junction" in check(home)["manual-drift"]
    assert sync(home) == 3
    assert (foreign / "LOCAL.txt").read_text(encoding="utf-8") == "не удалять"
    assert not _is_junction(foreign)

def test_targets_unknown_name_error(make_canon):
    import pytest as _pytest
    from codex_sync import render_all
    home = make_canon()
    (home / ".claude" / "codex-layer" / "targets.json").write_text(
        '{"enable": ["codex", "vscode"]}', encoding="utf-8")
    with _pytest.raises(ValueError, match="неизвестн"):
        render_all(home)

def test_targets_key_collision_error(make_canon, monkeypatch):
    import pytest as _pytest
    import codex_sync
    home = make_canon()
    monkeypatch.setitem(codex_sync.TARGETS, "fake",
                        {"render": lambda h: {"AGENTS.md": "x"}, "path": lambda h, k: None})
    (home / ".claude" / "codex-layer" / "targets.json").write_text(
        '{"enable": ["codex", "fake"]}', encoding="utf-8")
    with _pytest.raises(ValueError, match="коллизия"):
        codex_sync.render_all(home)

def test_targets_default_without_file(make_canon):
    from codex_sync import render_all
    home = make_canon()
    (home / ".claude" / "codex-layer" / "targets.json").unlink()
    assert "AGENTS.md" in render_all(home)      # обратная совместимость: дефолт ["codex"]

def test_diff_cmd_shows_unified_diff(make_canon, capsys):
    from codex_sync import sync, diff_cmd
    home = make_canon(); sync(home)
    (home / ".codex" / "AGENTS.md").write_text("ручная правка\n", encoding="utf-8", newline="\n")
    diff_cmd(home)
    out = capsys.readouterr().out
    assert "AGENTS.md" in out and "+ручная правка" in out.replace("+ ручная", "+ручная")

def test_base_tables_flow_into_managed_block(make_canon):
    import tomllib as _toml
    from codex_sync import sync
    home = make_canon()
    assert sync(home) == 0
    raw = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    from codex_sync import BEGIN, END
    block = raw.split(BEGIN)[1].split(END)[0]
    assert "[agents]" in block and "[mcp_servers.time]" in block
    assert block.index("[agents]") < block.index("[mcp_servers.time]")   # base перед MCP
    _toml.loads(raw.replace(BEGIN, "").replace(END, ""))                 # файл валиден

def test_base_collision_skipped_with_warn(make_canon, capsys):
    from codex_sync import render_all
    home = make_canon()
    cfg = home / ".codex" / "config.toml"
    cfg.write_text("x = 1\n[agents]\nmax_threads = 2\n", encoding="utf-8")
    payload = render_all(home)["config.toml#managed"]
    assert "[agents]" not in payload                                      # коллизия пропущена
    assert "[agents]" in capsys.readouterr().err                          # warn напечатан

def test_base_collision_with_trailing_comment_is_skipped(make_canon, capsys):
    from codex_sync import render_all
    home = make_canon()
    cfg = home / ".codex" / "config.toml"
    cfg.write_text("x = 1\n[agents] # user override\nmax_threads = 2\n", encoding="utf-8")

    payload = render_all(home)["config.toml#managed"]

    assert "[agents]" not in payload
    assert "[agents]" in capsys.readouterr().err

def test_nested_user_table_does_not_suppress_parent_base_table(make_canon, capsys):
    import tomllib as _toml
    from codex_sync import apply_managed_block, render_base_tables
    home = make_canon()
    cfg = home / ".codex" / "config.toml"
    outside = "x = 1\n[agents.foo]\nbar = 1\n"
    cfg.write_text(outside, encoding="utf-8", newline="\n")

    payload = render_base_tables(home)

    assert "[agents]" in payload
    assert "секция [agents]" not in capsys.readouterr().err
    _toml.loads(apply_managed_block(outside, payload))

def test_base_toplevel_key_rejected(make_canon):
    import pytest as _pytest
    from codex_sync import render_all
    home = make_canon()
    (home / ".claude" / "codex-layer" / "base.toml").write_text(
        'web_search = "cached"\n[agents]\nmax_threads = 6\n', encoding="utf-8")
    with _pytest.raises(ValueError, match="top-level"):
        render_all(home)

def test_broken_user_config_outside_block_does_not_crash(make_canon, capsys):
    from codex_sync import check, sync
    home = make_canon()
    sync(home)
    (home / ".codex" / "config.toml").write_text("[oops\nbroken = true\n", encoding="utf-8")
    res = check(home)                                  # не падает трейсбеком
    assert "config.toml#managed" in (res["canon-newer"] + res["manual-drift"])
    assert "фильтр коллизий пропущен" in capsys.readouterr().err
    assert sync(home) in (0, 3, 4)                     # штатный код, не исключение

def test_profiles_rendered_with_marker_and_manifest_coverage(make_canon):
    from codex_sync import sync, check
    home = make_canon()
    assert sync(home) == 0
    plus = home / ".codex" / "plus.config.toml"
    assert plus.exists()
    assert plus.read_text(encoding="utf-8").splitlines()[0].startswith("# generated-by: codex_sync")
    # ручная правка профиля → manual-drift
    plus.write_text(plus.read_text(encoding="utf-8") + "manual = true\n", encoding="utf-8", newline="\n")
    assert "plus.config.toml" in check(home)["manual-drift"]
    # правка канона профиля → canon-newer
    (home / ".claude" / "codex-layer" / "profiles" / "pro.toml").write_text(
        'model = "gpt-5.6-terra"\n', encoding="utf-8")
    assert "pro.config.toml" in check(home)["canon-newer"]

def test_profile_invalid_canon_toml_raises(make_canon):
    import pytest as _pytest, tomllib as _toml
    from codex_sync import render_all
    home = make_canon()
    (home / ".claude" / "codex-layer" / "profiles" / "plus.toml").write_text(
        'model = [broken', encoding="utf-8")
    with _pytest.raises(_toml.TOMLDecodeError):
        render_all(home)

def test_profiles_absent_dir_tolerated(make_canon):
    import shutil
    from codex_sync import render_all
    home = make_canon()
    shutil.rmtree(home / ".claude" / "codex-layer" / "profiles")
    out = render_all(home)
    assert "plus.config.toml" not in out and "AGENTS.md" in out

def test_sync_returns_4_and_keeps_file_on_invalid_result(make_canon, monkeypatch):
    import codex_sync
    home = make_canon()
    codex_sync.sync(home)
    before = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    # ломаем сборку: дубль таблицы внутри payload → итог невалиден, компоненты по отдельности валидны
    monkeypatch.setattr(codex_sync, "render_base_tables",
                        lambda h: "[dup]\nx = 1\n\n[dup]\nx = 2")
    assert codex_sync.sync(home) == 4
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == before

def test_fresh_machine_no_config_toml(make_canon):
    """Эпик 2, задача 4: свежая машина без ~/.codex/config.toml — sync создаёт
    файл из одного managed-блока (регрессия на ветки `if exists else ""`)."""
    import tomllib as _toml
    from codex_sync import sync, check, BEGIN
    home = make_canon()
    (home / ".codex" / "config.toml").unlink()
    assert sync(home) == 0
    raw = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert raw.startswith(BEGIN)                              # файл = один managed-блок
    from codex_sync import END
    _toml.loads(raw.replace(BEGIN, "").replace(END, ""))
    assert check(home)["canon-newer"] == [] and check(home)["manual-drift"] == []

# --- Эпик 3: оверлей доменного моста ---

def _fake_py_server(home, name="pyserv"):
    """Сервер с python-venv command в .claude.json + поддельный venv с багованным stdio.py."""
    import json as _json
    venv = home / "srv" / ".venv"
    p = venv / "Lib" / "site-packages" / "mcp" / "server" / "stdio.py"
    p.parent.mkdir(parents=True)
    p.write_text('stdout = anyio.wrap_file(TextIOWrapper(sys.stdout.buffer, encoding="utf-8"))\n',
                 encoding="utf-8")
    cj = home / ".claude.json"
    data = _json.loads(cj.read_text(encoding="utf-8"))
    data["mcpServers"][name] = {"command": str(venv / "Scripts" / "python.exe"),
                                "args": ["-m", "srv"]}
    cj.write_text(_json.dumps(data), encoding="utf-8")
    return venv

def test_overlay_extends_allow_with_bridge_options(make_canon):
    import tomllib as _toml
    from codex_sync import render_all, save_overlay
    home = make_canon()
    save_overlay(home, ["excel"])
    block = render_all(home)["config.toml#managed"]
    parsed = _toml.loads(block)
    assert parsed["mcp_servers"]["excel"]["required"] is False
    assert parsed["mcp_servers"]["excel"]["startup_timeout_sec"] == 60
    assert "time" in parsed["mcp_servers"]                       # дефолт остался
    assert "required" not in parsed["mcp_servers"]["time"]       # whitelist без bridge-опций

def test_overlay_roundtrip_and_empty_deletes_file(make_canon):
    from codex_sync import load_overlay, overlay_path, save_overlay
    home = make_canon()
    assert load_overlay(home) == []                              # файла нет
    save_overlay(home, ["b", "a"])
    assert load_overlay(home) == ["b", "a"] or load_overlay(home) == ["a", "b"]
    save_overlay(home, [])
    assert not overlay_path(home).exists() and load_overlay(home) == []

def test_overlay_corrupt_file_warns_and_empty(make_canon, capsys):
    from codex_sync import load_overlay, overlay_path, save_overlay
    home = make_canon()
    overlay_path(home).parent.mkdir(parents=True, exist_ok=True)
    overlay_path(home).write_text("{битый", encoding="utf-8")
    assert load_overlay(home) == []
    assert "оверлей" in capsys.readouterr().err

def test_overlay_wrong_types_warn_and_empty(make_canon, capsys):
    from codex_sync import load_overlay, overlay_path
    home = make_canon()
    overlay_path(home).parent.mkdir(parents=True, exist_ok=True)
    overlay_path(home).write_text('{"enable": "excel"}', encoding="utf-8")
    assert load_overlay(home) == []
    overlay_path(home).write_text('{"enable": [1, 2]}', encoding="utf-8")
    assert load_overlay(home) == []
    assert capsys.readouterr().err.count("оверлей") == 2

def test_overlay_no_false_drift_and_off_is_byte_identical(make_canon):
    from codex_sync import check, save_overlay, sync
    home = make_canon(); sync(home)
    base_cfg = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    save_overlay(home, ["excel"])
    res = check(home)
    assert res["manual-drift"] == []                             # включение моста ≠ дрейф
    assert "config.toml#managed" in res["canon-newer"]
    assert sync(home) == 0
    assert check(home)["canon-newer"] == [] and check(home)["manual-drift"] == []
    save_overlay(home, [])
    assert sync(home) == 0
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == base_cfg

def test_overlay_server_edit_tracked_in_inputs(make_canon):
    import json as _json
    from codex_sync import collect_inputs, save_overlay
    home = make_canon()
    save_overlay(home, ["excel"])
    h1 = collect_inputs(home)
    cj = home / ".claude.json"
    data = _json.loads(cj.read_text(encoding="utf-8"))
    data["mcpServers"]["excel"]["args"] = ["other"]
    cj.write_text(_json.dumps(data), encoding="utf-8")
    h2 = collect_inputs(home)
    assert h1[".claude.json#mcpServers"] != h2[".claude.json#mcpServers"]
    assert "codex-mcp-overlay" in h1                             # оверлей — вход манифеста

# --- Эпик 3: CLI mcp on/off/status ---

def test_mcp_on_patches_and_enables(make_canon, capsys):
    from codex_sync import load_overlay, mcp_cmd
    from mcp_crlf_patch import stdio_path, FIXED
    home = make_canon()
    venv = _fake_py_server(home)
    assert mcp_cmd(home, "on", ["pyserv"]) == 0
    assert load_overlay(home) == ["pyserv"]
    assert FIXED in stdio_path(venv).read_text(encoding="utf-8")   # патч применён
    cfg = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert "[mcp_servers.pyserv]" in cfg and "required = false" in cfg
    assert "рестартни Codex" in capsys.readouterr().out

def test_mcp_on_non_python_server_skips_patch(make_canon, capsys):
    from codex_sync import load_overlay, mcp_cmd
    home = make_canon()
    assert mcp_cmd(home, "on", ["excel"]) == 0                    # command=uvx — патч не нужен
    assert load_overlay(home) == ["excel"]
    assert "не требуется" in capsys.readouterr().out

def test_mcp_on_unknown_server_rejected(make_canon, capsys):
    from codex_sync import load_overlay, mcp_cmd, sync
    home = make_canon(); sync(home)
    before = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert mcp_cmd(home, "on", ["ghost"]) == 1
    assert load_overlay(home) == []                               # оверлей не тронут
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == before
    assert "ghost" in capsys.readouterr().err

def test_mcp_on_patch_failure_aborts_atomically(make_canon, capsys):
    from codex_sync import load_overlay, mcp_cmd, sync
    home = make_canon(); sync(home)
    venv = _fake_py_server(home)
    # незнакомый SDK → unknown-pattern → отказ
    from mcp_crlf_patch import stdio_path
    stdio_path(venv).write_text("другой код\n", encoding="utf-8")
    before = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    assert mcp_cmd(home, "on", ["pyserv"]) == 1
    assert load_overlay(home) == []
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == before
    assert "мост не включён" in capsys.readouterr().err

def test_mcp_off_and_status(make_canon, capsys):
    from codex_sync import load_overlay, mcp_cmd, sync
    home = make_canon(); sync(home)
    base_cfg = (home / ".codex" / "config.toml").read_text(encoding="utf-8")
    _fake_py_server(home)
    mcp_cmd(home, "on", ["pyserv"]); capsys.readouterr()
    assert mcp_cmd(home, "status", []) == 0
    out = capsys.readouterr().out
    assert "pyserv" in out and "already-ok" in out                # патч-статус в status
    assert mcp_cmd(home, "off", []) == 0                          # без имён = все
    assert load_overlay(home) == []
    assert (home / ".codex" / "config.toml").read_text(encoding="utf-8") == base_cfg

def test_mcp_on_requires_names(make_canon):
    from codex_sync import mcp_cmd
    assert mcp_cmd(make_canon(), "on", []) == 1


def test_effective_allow_deduplicates_overlay_and_whitelist():
    from codex_sync import effective_allow

    assert effective_allow(["time", "time"], ["excel", "time", "excel"]) == ["excel", "time"]


def test_save_overlay_validates_normalizes_and_uses_atomic_writer(make_canon, monkeypatch):
    import pytest
    import codex_sync
    from codex_sync import load_overlay, overlay_path, save_overlay

    home = make_canon()
    target = overlay_path(home)
    original_writer = codex_sync._write_atomic
    calls = []

    def tracked_writer(path, text):
        calls.append(path)
        original_writer(path, text)

    monkeypatch.setattr(codex_sync, "_write_atomic", tracked_writer)
    save_overlay(home, ["excel", "time", "excel"])

    assert calls == [target]
    assert load_overlay(home) == ["excel", "time"]
    before = target.read_bytes()
    for bad in ("excel", [""], ["excel", 1]):
        with pytest.raises(ValueError):
            save_overlay(home, bad)
    assert target.read_bytes() == before
    assert not target.with_name(target.name + ".tmp-codex-sync").exists()


def test_mcp_cmd_rejects_unknown_action_and_ghost_or_inactive_off(make_canon, capsys):
    from codex_sync import load_overlay, mcp_cmd

    home = make_canon()
    assert mcp_cmd(home, "enable", ["excel"]) == 1
    assert mcp_cmd(home, "status", ["excel"]) == 1
    assert mcp_cmd(home, "off", ["ghost"]) == 1
    assert mcp_cmd(home, "off", ["excel"]) == 1
    assert load_overlay(home) == []
    assert "неизвестное действие" in capsys.readouterr().err


def test_mcp_on_normalizes_duplicate_names(make_canon):
    from codex_sync import load_overlay, mcp_cmd

    home = make_canon()
    assert mcp_cmd(home, "on", ["excel", "excel"]) == 0
    assert load_overlay(home) == ["excel"]


def test_cli_argparse_routes_mcp_action_and_rejects_extra_arguments(make_canon, capsys):
    from codex_sync import main

    home = make_canon()
    assert main(["mcp", "status"], home=home) == 0
    assert main(["mcp", "on"], home=home) == 1
    assert main(["mcp", "status", "excel"], home=home) == 1
    assert main(["check", "unexpected"], home=home) == 2
    assert "только с mcp" in capsys.readouterr().err


def test_drift_hook_uses_shared_overlay_parser_via_patcher():
    hook = (pathlib.Path(__file__).parents[1] / "codex-drift-check.ps1").read_text(encoding="utf-8")

    assert "ConvertFrom-Json" not in hook
    assert "--overlay-names" in hook
    assert "--from-overlay --check" in hook


def test_canon_table_outside_managed_is_canon_newer_and_sync_relocates(make_canon):
    # Таблица канона ([mcp_servers.<whitelist>] или [agents.<native>]) оказалась
    # снаружи managed-блока (старый sync или App): значения те же, только место.
    # check — canon-newer, не manual-drift; sync переносит таблицу внутрь блока,
    # дубля нет, TOML валиден, повторный sync идемпотентен (вердикт Codex 2026-09-03).
    import re as _re
    import tomllib as _toml
    from codex_sync import BEGIN, END, check, sync
    home = make_canon()
    assert sync(home) == 0
    cfg = home / ".codex" / "config.toml"
    raw = cfg.read_text(encoding="utf-8")
    block = _re.search(_re.escape(BEGIN) + r"\n(.*?)\n" + _re.escape(END), raw, _re.S).group(1)
    section = _re.search(r"(?ms)^\[mcp_servers\.time\]\n(?:(?!^\[).*\n?)*", block).group(0)
    moved = raw.replace(block, block.replace(section, "").rstrip()) + "\n" + section.strip() + "\n"
    _toml.loads(moved.replace(BEGIN, "").replace(END, ""))
    cfg.write_text(moved, encoding="utf-8")

    res = check(home)
    assert "config.toml#managed" in res["canon-newer"]
    assert "config.toml#managed" not in res["manual-drift"]

    assert sync(home) == 0
    merged = cfg.read_text(encoding="utf-8")
    _toml.loads(merged.replace(BEGIN, "").replace(END, ""))
    assert merged.count("[mcp_servers.time]") == 1
    assert merged.index("[mcp_servers.time]") < merged.index(END)
    assert "x = 1" in merged                                  # чужой top-level ключ сохранён
    assert sync(home) == 0
    assert check(home)["manual-drift"] == [] and check(home)["canon-newer"] == []


def test_user_table_with_other_name_outside_managed_survives_relocation(make_canon):
    # Перенос касается только таблиц из payload канона: чужая [agents.foo] снаружи
    # блока остаётся на месте и не считается дрейфом.
    import tomllib as _toml
    from codex_sync import check, sync
    home = make_canon()
    assert sync(home) == 0
    cfg = home / ".codex" / "config.toml"
    cfg.write_text(cfg.read_text(encoding="utf-8") + "\n[agents.foo]\nbar = 1\n", encoding="utf-8")
    assert check(home)["manual-drift"] == []
    assert sync(home) == 0
    merged = cfg.read_text(encoding="utf-8")
    assert merged.count("[agents.foo]") == 1 and "bar = 1" in merged
    _toml.loads(merged.replace("# >>> claude-base managed >>>", "").replace("# <<< claude-base managed <<<", ""))
