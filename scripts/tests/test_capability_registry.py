# -*- coding: utf-8 -*-
"""Coverage канонического capability registry Epic 4b."""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parents[1]))

CLAUDE = pathlib.Path(__file__).parents[2]
HOME = CLAUDE.parent


def _role_names():
    names = set()
    for path in (CLAUDE / "agents").glob("*.md"):
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("name:"):
                names.add(line.partition(":")[2].strip())
                break
    return names


def test_registry_covers_exact_roles_skills_and_permissions():
    from codex_sync import load_capability_registry

    registry = load_capability_registry(HOME)
    roles = registry["_roles"]
    assert set(roles) == _role_names()
    assert len(roles) == 16
    assert {name for name, item in roles.items() if item["permission_class"] == "ro"} == {
        "audit-rd-section", "auditor", "excel-validator", "norm-lookup",
        "pdf-reviewer", "rd-coordinator", "word-checker",
    }
    assert sum(item["permission_class"] == "rw" for item in roles.values()) == 9

    manifest = json.loads((CLAUDE / "codex-layer" / "skills-manifest.json").read_text(encoding="utf-8"))
    assert {item["skill_id"] for item in registry["skill_adapters"]} == (
        set(manifest["enable"]) | set(manifest["skip_reason"])
    )
    assert len(manifest["enable"]) == 11 and len(manifest["skip_reason"]) == 26
    for skill in registry["skill_adapters"]:
        assert skill["optional_capabilities"] == []
        enabled = skill["skill_id"] in manifest["enable"]
        assert skill["manifest_state"] == ("enabled" if enabled else "skipped")
        if not enabled:
            assert skill["skip_reason"] == manifest["skip_reason"][skill["skill_id"]]


def test_registry_required_capabilities_are_honest():
    from codex_sync import load_capability_registry

    registry = load_capability_registry(HOME)
    for adapter in [*registry["role_adapters"], *registry["skill_adapters"]]:
        for capability_id in adapter["required_capabilities"]:
            capability = registry["_capabilities"][capability_id]
            assert capability["providers"] or capability["verification"]["status"] == "blocked"
    for capability in registry["capabilities"]:
        assert capability["access"] in {"read", "write", "execute"}
        assert capability["fallback"] and capability["escalation"]
        for provider in capability["providers"]:
            assert provider["environments"] == ["claude", "codex"]
            assert provider["availability"] in {"available", "on-demand", "blocked"}
            if provider["profile"] == "Revit/AutoCAD":
                assert provider["enabled_by_default"] is False
                assert provider["availability"] == "on-demand"
                assert capability["verification"]["status"] in {"forward-test", "live"}
    assert registry["_capabilities"]["pdf.write"]["verification"]["status"] == "blocked"
    assert registry["_capabilities"]["revit.inspect"]["verification"]["status"] == "live"
    assert registry["_capabilities"]["revit.execute"]["verification"]["status"] == "forward-test"
    assert registry["_capabilities"]["revit.modify"]["verification"]["status"] == "forward-test"
    assert registry["_capabilities"]["autocad.inspect"]["verification"]["status"] == "live"


def test_converter_has_no_raw_mcp_and_rejects_unknown_identifier():
    from codex_sync import (
        _map_raw_tools,
        collect_agent_tomls,
        load_capability_registry,
        render_target_codex,
    )

    registry = load_capability_registry(HOME)
    rendered = render_target_codex(HOME)
    agents = [value for key, value in rendered.items() if key.startswith("agents/")]
    assert set(key for key in rendered if key.startswith("agents/")) == {
        "agents/auditor.toml"
    }

    catalog = collect_agent_tomls(CLAUDE / "agents", registry)
    assert len(catalog) == 16
    assert "mcp__" not in "\n".join(catalog.values())
    assert sum('sandbox_mode = "read-only"' in value for value in catalog.values()) == 7
    with pytest.raises(ValueError, match="unresolved raw MCP tool"):
        _map_raw_tools("mcp__unknown__thing", registry)


def test_real_registry_render_exposes_complete_adapter_contract():
    """Каталог остаётся полным, но в стартовый Codex-пакет входит только active-набор."""
    from codex_sync import collect_agent_tomls, load_capability_registry, render_target_codex

    catalog = collect_agent_tomls(CLAUDE / "agents", load_capability_registry(HOME))
    assert set(path.removesuffix(".toml") for path in catalog) == _role_names()
    rendered = render_target_codex(HOME)
    for role_id in ("auditor",):
        text = rendered[f"agents/{role_id}.toml"]
        for field in (
            "[Capability adapter]", "required:", "optional:",
            "permission_class:", "input_contract:", "output_contract:",
            "verification.claude:", "verification.codex:", "fallback:", "handoff:",
        ):
            assert field in text, f"{role_id}: {field}"


def test_real_manifest_renders_minimal_codex_hooks():
    from codex_sync import render_target_codex

    rendered = render_target_codex(HOME)
    hooks = json.loads(rendered["hooks.json"])["hooks"]
    assert set(hooks) == {"SessionStart", "Stop"}
    serialized = json.dumps(hooks, ensure_ascii=False)
    assert "auto-pull.ps1" in serialized
    assert "auto-push.ps1" in serialized
    for forbidden in (
        "log-tool-usage",
        "project-memory",
        "graph-staleness",
        "codex_context_governor",
    ):
        assert forbidden not in serialized


def test_every_raw_identifier_in_actual_agents_resolves_by_registry():
    """TOOL_MAP покрывает каждый raw MCP id из исходных 16 ролей."""
    import re
    from codex_sync import _map_raw_tools, load_capability_registry

    registry = load_capability_registry(HOME)
    source = "\n".join(path.read_text(encoding="utf-8") for path in (CLAUDE / "agents").glob("*.md"))
    raw_identifiers = set(re.findall(r"mcp__[A-Za-z0-9-]+__[A-Za-z0-9_*\\]+", source))
    assert raw_identifiers
    for raw_identifier in raw_identifiers:
        assert "mcp__" not in _map_raw_tools(raw_identifier, registry)


def test_registry_and_schema_are_tracked_inputs():
    from codex_sync import collect_inputs

    inputs = collect_inputs(HOME)
    assert "codex-layer/capability-registry.json" in inputs
    assert "codex-layer/capability-registry.schema.json" in inputs
    assert "base-manifest.json" in inputs
    assert "context-budget.json" in inputs
