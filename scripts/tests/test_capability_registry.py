# -*- coding: utf-8 -*-
"""Coverage канонического capability registry Epic 4b."""
import json
import pathlib
import re
import sys
import tomllib

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
    assert not (set(manifest["enable"]) & set(manifest["skip_reason"]))
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
    from codex_sync import _map_raw_tools, load_capability_registry, render_target_codex

    registry = load_capability_registry(HOME)
    rendered = render_target_codex(HOME)
    agents = [value for key, value in rendered.items() if key.startswith("agents/")]
    assert len(agents) == 16
    assert "mcp__" not in "\n".join(agents)
    assert sum('sandbox_mode = "read-only"' in value for value in agents) == 7
    with pytest.raises(ValueError, match="unresolved raw MCP tool"):
        _map_raw_tools("mcp__unknown__thing", registry)


def test_real_registry_render_exposes_complete_adapter_contract():
    """Реальный канон, а не мини-фикстура, порождает все 16 адаптеров."""
    from codex_sync import load_capability_registry, render_target_codex

    registry = load_capability_registry(HOME)
    native_roles = set(registry["codex_native"]["roles"])
    rendered = render_target_codex(HOME)
    for role_id in _role_names():
        text = rendered[f"agents/{role_id}.toml"]
        if role_id in native_roles:
            fields = (
                "[Codex-native adapter]", "required_tools:", "optional_tools:",
                "permission_class:", "input_contract:", "output_contract:",
                "verification.codex:", "fallback:", "handoff:",
            )
        else:
            fields = (
                "[Capability adapter]", "required:", "optional:",
                "permission_class:", "input_contract:", "output_contract:",
                "verification.claude:", "verification.codex:", "fallback:", "handoff:",
            )
        for field in fields:
            assert field in text, f"{role_id}: {field}"


def test_three_codex_native_profiles_use_real_routes_only():
    from codex_sync import load_capability_registry, render_target_codex

    registry = load_capability_registry(HOME)
    assert registry["codex_native"]["roles"] == ["auditor", "norm-lookup", "pto-engineer"]
    assert registry["codex_native"]["agent_names"] == {
        "auditor": "auditor", "norm-lookup": "norm_lookup", "pto-engineer": "pto_engineer",
    }
    assert set(registry["codex_native"]["instruction_files"]) == {
        "auditor", "norm-lookup", "pto-engineer",
    }
    rendered = render_target_codex(HOME)
    managed = rendered["config.toml#managed"]
    managed_data = tomllib.loads(managed)
    for role_id in registry["codex_native"]["roles"]:
        text = rendered[f"agents/{role_id}.toml"]
        parsed = tomllib.loads(text)
        instructions = parsed["developer_instructions"]
        agent_name = registry["codex_native"]["agent_names"][role_id]
        assert "`shell_command`" in text
        assert "`functions.exec`" not in text
        assert "capability `" not in text
        assert "[Capability adapter]" not in text
        assert "Основной Claude" not in text
        assert "основному Claude" not in text
        assert not re.search(r"\b(?:Read|Write|Edit|Glob|Grep|Bash)\b", instructions)
        assert "mcp__" not in text
        assert f"name = '{agent_name}'" in text
        assert f"[agents.{agent_name}]" in managed
        assert managed_data["agents"][agent_name]["config_file"] == f"agents/{role_id}.toml"
        for stale in (
            "`web.extract`", "web_extract_", "fetch-MCP", "browser_navigate",
            "get_document_text", "read_data", "pdf_info", "pdf_read_pages",
            "find_text_in_document", "search_and_replace", "`скилл `",
        ):
            assert stale not in text, f"{role_id}: stale {stale}"
    assert "`web-access`" in rendered["agents/norm-lookup.toml"]
    assert "`browser:control-in-app-browser`" in rendered["agents/norm-lookup.toml"]
    assert "`documents:documents`" in rendered["agents/auditor.toml"]
    assert "`spreadsheets:Spreadsheets`" in rendered["agents/pto-engineer.toml"]


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
