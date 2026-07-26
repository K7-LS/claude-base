# -*- coding: utf-8 -*-
"""Офлайн-сборщик и диагност компактной базы Claude/Codex/OpenCode."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path, PurePosixPath
from typing import Any


TARGET_ROOTS = {
    "claude": (".claude/",),
    "codex": (".codex/", ".agents/"),
    "opencode": (".config/opencode/", ".local/bin/"),
}


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path}: верхний JSON должен быть объектом")
    return value


def load_manifest(repo: Path) -> dict[str, Any]:
    manifest = _read_json(repo / "base-manifest.json")
    if manifest.get("schema") != 1:
        raise ValueError("base-manifest.json: поддерживается только schema=1")
    targets = manifest.get("targets")
    if not isinstance(targets, dict) or set(targets) != set(TARGET_ROOTS):
        raise ValueError("base-manifest.json: ожидаются claude, codex и opencode")
    if "kimi" in json.dumps(manifest, ensure_ascii=False).lower():
        raise ValueError("Kimi не является отдельным target новой базы")
    sync = manifest.get("sync", {})
    if (
        sync.get("direction") != "hub-to-consumer"
        or sync.get("consumer_push") is not False
        or sync.get("consumer_feedback_upload") is not False
        or sync.get("consumer_session_upload") is not False
    ):
        raise ValueError("base-manifest.json: sync должен быть односторонним hub-to-consumer")
    return manifest


def _metadata_files(repo: Path, target: str, spec: dict[str, Any]) -> dict[str, str]:
    manifest = load_manifest(repo)
    target_manifest = {
        "schema": 1,
        "name": manifest["name"],
        "target": target,
        "active_agents": spec["active_agents"],
        "active_skills": spec["active_skills"],
        "sync": manifest["sync"],
        "secrets": manifest["secrets"],
    }
    return {
        "target-manifest.json": json.dumps(target_manifest, ensure_ascii=False, indent=2) + "\n",
        "context-budget.json": (repo / "context-budget.json").read_text(encoding="utf-8"),
    }


def _copy_tree(source: Path, prefix: str) -> dict[str, str]:
    output: dict[str, str] = {}
    if not source.exists():
        raise ValueError(f"Компонент отсутствует: {source}")
    for file_path in sorted(p for p in source.rglob("*") if p.is_file()):
        if any(part in {"__pycache__", ".pytest_cache", ".git"} for part in file_path.parts):
            continue
        if file_path.suffix.lower() in {".pyc", ".pyo", ".pyd"}:
            continue
        relative = file_path.relative_to(source).as_posix()
        try:
            output[f"{prefix}/{relative}"] = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"Активный компонент содержит бинарный файл: {file_path}") from exc
    return output


def _target_agent_files(repo: Path, target: str, names: list[str]) -> dict[str, str]:
    extension = {"claude": ".md", "codex": ".toml", "opencode": ".md"}[target]
    destination = {
        "claude": ".claude/agents",
        "codex": ".codex/agents",
        "opencode": ".config/opencode/agents",
    }[target]
    output: dict[str, str] = {}
    for name in names:
        source = repo / "targets" / target / "agents" / f"{name}{extension}"
        if not source.is_file():
            raise ValueError(f"Нет нативного агента {target}/{name}")
        output[f"{destination}/{name}{extension}"] = source.read_text(encoding="utf-8")
    return output


def _active_skills(repo: Path, target: str, names: list[str]) -> dict[str, str]:
    destination = {
        "claude": ".claude/skills",
        "codex": ".agents/skills",
        "opencode": ".config/opencode/skills",
    }[target]
    output: dict[str, str] = {}
    for name in names:
        output.update(_copy_tree(repo / "skills" / name, f"{destination}/{name}"))
    return output


def render_target(repo: Path, target: str) -> dict[str, str]:
    """Вернуть относительный путь home → содержимое. Функция ничего не пишет."""
    repo = repo.resolve()
    manifest = load_manifest(repo)
    if target not in TARGET_ROOTS:
        raise ValueError(f"Неизвестный target {target!r}")
    spec = manifest["targets"][target]
    core = (repo / "core" / "AGENTS.core.md").read_text(encoding="utf-8").rstrip() + "\n"
    layer = (repo / spec["rules"]).read_text(encoding="utf-8").rstrip() + "\n"
    metadata = _metadata_files(repo, target, spec)
    output: dict[str, str] = {}

    if target == "claude":
        output[".claude/core/AGENTS.core.md"] = core
        output[".claude/CLAUDE.md"] = layer
        meta_root = ".claude/.base"
    elif target == "codex":
        output[".codex/AGENTS.md"] = core + "\n" + layer
        meta_root = ".codex/.base"
    else:
        output[".config/opencode/AGENTS.md"] = core + "\n" + layer
        config = _read_json(repo / "targets" / "opencode" / "opencode.json")
        skill_permissions = config.setdefault("permission", {}).setdefault("skill", {})
        skill_permissions["*"] = "deny"
        for name in spec["active_skills"]:
            skill_permissions[name] = "allow"
        output[".config/opencode/opencode.json"] = (
            json.dumps(config, ensure_ascii=False, indent=2) + "\n"
        )
        output[".local/bin/opencode-base.ps1"] = (
            repo / "targets" / "opencode" / "opencode-base.ps1"
        ).read_text(encoding="utf-8")
        meta_root = ".config/opencode/.base"

    output.update(_target_agent_files(repo, target, list(spec["active_agents"])))
    output.update(_active_skills(repo, target, list(spec["active_skills"])))
    for name, text in metadata.items():
        output[f"{meta_root}/{name}"] = text
    return output


def estimate_tokens(text: str) -> int:
    """Консервативная vendor-neutral оценка без сетевого токенизатора."""
    return math.ceil(len(text.encode("utf-8")) / 3)


def _frontmatter_description(text: str) -> str:
    if not text.startswith("---"):
        return ""
    for line in text.splitlines()[1:]:
        if line.strip() == "---":
            break
        if line.startswith("description:"):
            return line.split(":", 1)[1].strip().strip("\"'")
    return ""


def _catalog_text(repo: Path, target: str) -> str:
    manifest = load_manifest(repo)
    spec = manifest["targets"][target]
    parts: list[str] = []
    extension = {"claude": ".md", "codex": ".toml", "opencode": ".md"}[target]
    for name in spec["active_agents"]:
        text = (repo / "targets" / target / "agents" / f"{name}{extension}").read_text(
            encoding="utf-8"
        )
        description = _frontmatter_description(text)
        if target == "codex":
            for line in text.splitlines():
                if line.startswith("description = "):
                    description = line.split("=", 1)[1].strip().strip('"')
                    break
        parts.append(f"agent:{name}:{description}")
    for name in spec["active_skills"]:
        text = (repo / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        parts.append(f"skill:{name}:{_frontmatter_description(text)}")
    return "\n".join(parts)


def audit_rendered_context(
    repo: Path, target: str, rendered: dict[str, str] | None = None
) -> dict[str, Any]:
    rendered = rendered or render_target(repo, target)
    manifest = load_manifest(repo)
    budget = _read_json(repo / "context-budget.json")
    limits = budget["limits"]
    core = (repo / "core" / "AGENTS.core.md").read_text(encoding="utf-8")
    layer = (repo / manifest["targets"][target]["rules"]).read_text(encoding="utf-8")
    catalog = _catalog_text(repo, target)
    segments = {
        "core_tokens": estimate_tokens(core),
        "target_tokens": estimate_tokens(layer),
        "catalog_tokens": estimate_tokens(catalog),
    }
    startup_total = sum(segments.values())
    checks = {
        name: value <= int(limits[name])
        for name, value in segments.items()
    }
    checks["startup_total_tokens"] = startup_total <= int(limits["startup_total_tokens"])
    return {
        "target": target,
        "pass": all(checks.values()),
        "estimator": budget["estimator"],
        "segments": segments,
        "startup_total_tokens": startup_total,
        "limits": limits,
        "checks": checks,
        "rendered_files": len(rendered),
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def doctor(
    repo: Path,
    target: str,
    home: Path,
    model_capabilities: dict[str, Any] | None = None,
    required_capabilities: list[str] | None = None,
) -> dict[str, Any]:
    """Сверка fake/live home без чтения содержимого auth-файлов."""
    expected = render_target(repo, target)
    missing: list[str] = []
    drift: list[str] = []
    for relative, text in expected.items():
        path = home / PurePosixPath(relative)
        if not path.is_file():
            missing.append(relative)
            continue
        try:
            actual = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            drift.append(relative)
            continue
        if _sha256(actual) != _sha256(text):
            drift.append(relative)
    launcher = expected.get(".local/bin/opencode-base.ps1", "")
    flags = (
        "OPENCODE_DISABLE_CLAUDE_CODE",
        "OPENCODE_DISABLE_CLAUDE_CODE_PROMPT",
        "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS",
    )
    auth_path = home / ".local" / "share" / "opencode" / "auth.json"
    required_capabilities = required_capabilities or []
    model_report: dict[str, Any] = {
        "checked": model_capabilities is not None,
        "model": None,
        "required": required_capabilities,
        "missing": [],
        "fallback": None,
    }
    if model_capabilities is not None:
        capabilities = model_capabilities.get("capabilities")
        if not isinstance(capabilities, dict):
            raise ValueError("model capabilities: поле capabilities должно быть объектом")
        model_report["model"] = model_capabilities.get("model")
        model_report["missing"] = [
            name for name in required_capabilities if capabilities.get(name) is not True
        ]

    report: dict[str, Any] = {
        "target": target,
        "healthy": not missing and not drift and not model_report["missing"],
        "missing": missing,
        "drift": drift,
        "context": audit_rendered_context(repo, target, expected),
        "auth": {"configured": auth_path.is_file() if target == "opencode" else False},
        "model": model_report,
    }
    if target == "opencode":
        report["claude_compatibility"] = {
            "launcher_enforced": all(flag in launcher for flag in flags)
        }
    return report


def verify(repo: Path, targets: list[str] | None = None) -> dict[str, Any]:
    manifest = load_manifest(repo)
    selected = targets or list(manifest["targets"])
    reports = {name: audit_rendered_context(repo, name) for name in selected}
    return {
        "pass": all(report["pass"] for report in reports.values()),
        "targets": reports,
        "sync": manifest["sync"],
    }


def _safe_destination(root: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"Небезопасный путь рендера: {relative}")
    destination = (root / pure).resolve()
    if root.resolve() not in destination.parents:
        raise ValueError(f"Путь вышел за output: {relative}")
    return destination


def write_rendered(output: Path, rendered: dict[str, str]) -> None:
    output.mkdir(parents=True, exist_ok=True)
    for relative, text in rendered.items():
        destination = _safe_destination(output, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8", newline="\n")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="base", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "audit-context", "doctor"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--target", required=True, choices=sorted(TARGET_ROOTS))
        if name == "render":
            cmd.add_argument("--output", required=True, type=Path)
        if name == "doctor":
            cmd.add_argument("--home", required=True, type=Path)
            cmd.add_argument("--model-capabilities", type=Path)
            cmd.add_argument("--require", action="append", default=[])
    verify_cmd = sub.add_parser("verify")
    verify_cmd.add_argument("--target", action="append", choices=sorted(TARGET_ROOTS))
    audit_cmd = sub.add_parser("audit-transcript")
    audit_cmd.add_argument("transcript", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo = Path(__file__).resolve().parents[1]
    try:
        if args.command == "render":
            rendered = render_target(repo, args.target)
            write_rendered(args.output, rendered)
            result: dict[str, Any] = {
                "target": args.target,
                "output": str(args.output.resolve()),
                "files": len(rendered),
                "context": audit_rendered_context(repo, args.target, rendered),
            }
        elif args.command == "audit-context":
            result = audit_rendered_context(repo, args.target)
        elif args.command == "doctor":
            model_capabilities = (
                _read_json(args.model_capabilities)
                if args.model_capabilities
                else None
            )
            result = doctor(
                repo,
                args.target,
                args.home.resolve(),
                model_capabilities=model_capabilities,
                required_capabilities=args.require,
            )
        elif args.command == "verify":
            result = verify(repo, args.target)
        else:
            from token_audit import audit_transcript

            result = audit_transcript(args.transcript)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.command in {"audit-context", "verify"}:
        return 0 if result["pass"] else 1
    if args.command == "doctor":
        return 0 if result["healthy"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
