# -*- coding: utf-8 -*-
"""Контракты компактной трёхклиентной базы."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _copy_rendered(rendered: dict[str, str], home: Path) -> None:
    for relative, text in rendered.items():
        target = home / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8", newline="\n")


def test_manifest_declares_exact_native_targets_without_kimi():
    manifest = json.loads((REPO / "base-manifest.json").read_text(encoding="utf-8"))

    assert manifest["schema"] == 1
    assert set(manifest["targets"]) == {"claude", "codex", "opencode"}
    assert manifest["sync"]["direction"] == "hub-to-consumer"
    assert manifest["sync"]["consumer_push"] is False
    assert manifest["sync"]["consumer_feedback_upload"] is False
    assert manifest["sync"]["consumer_session_upload"] is False
    assert "kimi" not in json.dumps(manifest, ensure_ascii=False).lower()


@pytest.mark.parametrize("target", ["claude", "codex", "opencode"])
def test_each_target_renders_only_native_paths_and_stays_within_budget(target):
    from base_cli import audit_rendered_context, render_target

    rendered = render_target(REPO, target)
    report = audit_rendered_context(REPO, target, rendered)

    assert rendered
    assert report["pass"] is True, report
    assert all("auth.json" not in path.lower() for path in rendered)

    roots = {
        "claude": (".claude/",),
        "codex": (".codex/", ".agents/"),
        "opencode": (".config/opencode/", ".local/bin/"),
    }
    assert all(path.startswith(roots[target]) for path in rendered)


def test_codex_target_contains_no_claude_only_vocabulary():
    from base_cli import render_target

    joined = "\n".join(render_target(REPO, "codex").values())
    forbidden = ("AskUserQuestion", "WebFetch", "mcp__", "CLAUDE.md", "~/.claude/skills")
    assert not any(term in joined for term in forbidden)


def test_legacy_codex_sync_uses_the_same_compact_native_layer():
    assert (REPO / "codex-layer" / "AGENTS.codex.md").read_text(
        encoding="utf-8"
    ) == (REPO / "targets" / "codex" / "AGENTS.md").read_text(encoding="utf-8")


def test_live_claude_entry_is_the_compact_native_layer():
    assert (REPO / "CLAUDE.md").read_text(encoding="utf-8") == (
        REPO / "targets" / "claude" / "CLAUDE.md"
    ).read_text(encoding="utf-8")


def test_opencode_target_is_provider_neutral_and_disables_claude_fallback():
    from base_cli import render_target

    rendered = render_target(REPO, "opencode")
    config = json.loads(rendered[".config/opencode/opencode.json"])
    launcher = rendered[".local/bin/opencode-base.ps1"]

    assert "model" not in config
    assert "provider" not in config
    assert config["mcp"] == {}
    assert config["permission"]["edit"] == "ask"
    assert config["permission"]["bash"] == "ask"
    assert config["permission"]["skill"]["*"] == "deny"
    assert set(config["permission"]["skill"].values()) <= {"allow", "deny", "ask"}
    assert "OPENCODE_DISABLE_CLAUDE_CODE" in launcher
    assert "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT" in launcher
    assert "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS" in launcher
    assert "auth.json" not in launcher


def test_render_contains_only_manifest_active_agents_and_skills():
    from base_cli import render_target

    manifest = json.loads((REPO / "base-manifest.json").read_text(encoding="utf-8"))
    for target in manifest["targets"]:
        rendered = render_target(REPO, target)
        agent_names = {
            Path(path).stem
            for path in rendered
            if "/agents/" in path and path.endswith((".md", ".toml"))
        }
        skill_names = {
            Path(path).parts[-2]
            for path in rendered
            if "/skills/" in path and path.endswith("/SKILL.md")
        }
        expected = manifest["targets"][target]
        assert agent_names == set(expected["active_agents"])
        assert skill_names == set(expected["active_skills"])


def test_native_auditors_do_not_force_model_or_reasoning_tier():
    claude = (REPO / "targets" / "claude" / "agents" / "auditor.md").read_text(
        encoding="utf-8"
    )
    codex = (REPO / "targets" / "codex" / "agents" / "auditor.toml").read_text(
        encoding="utf-8"
    )
    opencode = (REPO / "targets" / "opencode" / "agents" / "auditor.md").read_text(
        encoding="utf-8"
    )

    assert "\nmodel:" not in claude
    assert "\nmodel =" not in codex
    assert "reasoning_effort" not in codex
    assert "\nmodel:" not in opencode


def test_cli_render_is_offline_and_writes_only_requested_output(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPTS / "base_cli.py"),
            "render",
            "--target",
            "opencode",
            "--output",
            str(tmp_path),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / ".config" / "opencode" / "AGENTS.md").is_file()
    assert (tmp_path / ".config" / "opencode" / "opencode.json").is_file()
    assert not (tmp_path / ".local" / "share" / "opencode" / "auth.json").exists()


def test_doctor_accepts_fake_home_and_never_reads_real_home(tmp_path, monkeypatch):
    from base_cli import doctor, render_target

    fake_home = tmp_path / "fake-home"
    _copy_rendered(render_target(REPO, "opencode"), fake_home)
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "must-not-be-read"))
    monkeypatch.setenv("HOME", str(tmp_path / "must-not-be-read"))

    report = doctor(REPO, "opencode", fake_home)

    assert report["healthy"] is True, report
    assert report["auth"]["configured"] in {True, False}
    assert "value" not in report["auth"]
    assert report["claude_compatibility"]["launcher_enforced"] is True


def test_doctor_fails_closed_on_missing_model_capability_without_fallback(tmp_path):
    from base_cli import doctor, render_target

    fake_home = tmp_path / "fake-home"
    _copy_rendered(render_target(REPO, "opencode"), fake_home)
    capabilities = {
        "model": "openai/example",
        "capabilities": {"tools": False, "vision": True, "reasoning": True},
    }

    report = doctor(
        REPO,
        "opencode",
        fake_home,
        model_capabilities=capabilities,
        required_capabilities=["tools"],
    )

    assert report["healthy"] is False
    assert report["model"]["missing"] == ["tools"]
    assert report["model"]["fallback"] is None


def test_cli_simple_prompt_policy_is_zero_automation():
    policy = json.loads((REPO / "context-budget.json").read_text(encoding="utf-8"))
    simple = policy["simple_prompt"]

    assert simple == {"tool_calls": 0, "subagents": 0, "reviewers": 0}

def test_startup_context_budget_is_deliberately_small():
    policy = json.loads((REPO / "context-budget.json").read_text(encoding="utf-8"))
    limits = policy["limits"]

    assert limits["core_tokens"] <= 1800
    assert limits["target_tokens"] <= 800
    assert limits["catalog_tokens"] <= 500
    assert limits["startup_total_tokens"] <= 3000


def test_legacy_feedback_transport_is_not_part_of_active_base():
    forbidden_paths = (
        REPO / "scripts" / "feedback-collector.ps1",
        REPO / "scripts" / "pull-feedback.ps1",
        REPO / "scripts" / "Set-FeedbackToken.ps1",
    )
    assert not any(path.exists() for path in forbidden_paths)

    active = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            REPO / "CLAUDE.md",
            REPO / "README.md",
            REPO / "commands" / "sync-base.md",
            REPO / "scripts" / "auto-push.ps1",
        )
    )
    forbidden_terms = ("feedback-collector", "feedback-pending", "pull-feedback.ps1")
    assert not any(term in active for term in forbidden_terms)


def test_consumer_autopush_is_explicit_read_only_noop():
    script = (REPO / "scripts" / "auto-push.ps1").read_text(encoding="utf-8")

    assert "consumer read-only" in script
    assert "feedback-collector" not in script
    assert "$isDeveloper" in script
    assert "exit 0" in script


def test_hub_autopush_whitelists_all_authoritative_rework_sources():
    script = (REPO / "scripts" / "auto-push.ps1").read_text(encoding="utf-8")

    for managed_path in (
        "'base-manifest.json'",
        "'context-budget.json'",
        "'core'",
        "'targets'",
        "'codex-layer'",
    ):
        assert managed_path in script


def test_auto_pull_enforces_no_push_remote_for_consumers():
    script = (REPO / "scripts" / "auto-pull.ps1").read_text(encoding="utf-8")

    assert ".developer-marker" in script
    assert "NO_PUSH_CONSUMER" in script
    assert "remote set-url --push" in script


def test_legacy_verifier_checks_new_base_and_is_role_aware():
    script = (REPO / "scripts" / "verify-claude-base.ps1").read_text(encoding="utf-8")

    assert "base-manifest.json" in script
    assert "context-budget.json" in script
    assert "base_cli.py" in script and "verify" in script
    assert "NO_PUSH_CONSUMER" in script
    assert ".developer-marker" in script
    assert "feedback-collector" not in script
    assert "auto-push при закрытии чата" not in script


def test_shared_claude_settings_do_not_force_expensive_automation():
    settings = json.loads((REPO / "settings.shared.json").read_text(encoding="utf-8"))

    for retired in (
        "effortLevel",
        "enabledPlugins",
        "extraKnownMarketplaces",
        "autoMode",
        "agentPushNotifEnabled",
    ):
        assert retired not in settings
    assert set(settings["hooks"]) == {"SessionStart", "SessionEnd"}
    serialized = json.dumps(settings["hooks"], ensure_ascii=False)
    assert "auto-pull.ps1" in serialized
    assert "auto-push.ps1" in serialized
    for forbidden in (
        "UserPromptSubmit",
        "PostToolUse",
        "routing-detector",
        "grilling-detector",
        "understanding-map-detector",
        "log-tool-usage",
    ):
        assert forbidden not in serialized


def test_settings_merge_retires_legacy_forced_keys_once(tmp_path):
    fake_home = tmp_path / "home"
    claude = fake_home / ".claude"
    claude.mkdir(parents=True)
    (claude / "settings.shared.json").write_text(
        (REPO / "settings.shared.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (claude / "settings.json").write_text(
        json.dumps(
            {
                "theme": "dark",
                "effortLevel": "xhigh",
                "enabledPlugins": {"legacy": True},
                "autoMode": {"allow": ["legacy"]},
            }
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env["USERPROFILE"] = str(fake_home)

    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SCRIPTS / "merge-shared-settings.ps1"),
        ],
        cwd=REPO,
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    merged = json.loads((claude / "settings.json").read_text(encoding="utf-8-sig"))
    assert merged["theme"] == "dark"
    assert "effortLevel" not in merged
    assert "enabledPlugins" not in merged
    assert "autoMode" not in merged
    assert set(merged["hooks"]) == {"SessionStart", "SessionEnd"}
    assert (claude / ".local-state" / "shared-settings-v2-migrated.flag").is_file()
