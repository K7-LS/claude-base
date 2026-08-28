#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""map_store.py — хранение канонической карты понимания в ядре проекта.

Контракт (зеркальное решение Claude+Codex, 2026-08-28):
- Экземпляр: <selected-core>/understanding-map.json. Файл ОПЦИОНАЛЕН:
  отсутствие — норма, в признаки валидности ядра не входит.
- Запись: plan (dry-run, по умолчанию ничего не пишет) → apply
  (backup → временный файл → atomic replace). Существующий bootstrap ядра
  этот инструмент не трогает.
- CAS: revision — монотонное целое; apply поверх существующей карты требует
  --base-revision, несовпадение — MAP_CONFLICT (exit 3), автоматического
  merge нет. Ревизию записи назначает store (base+1; создание — 1).
- Более новая schema_version на диске — UNSUPPORTED_SCHEMA (exit 4):
  карта открывается read-only, файл не переписывается.
- Неизвестные поля входного документа сохраняются как есть.

Команды:
  read  --core <dir>                          напечатать карту (или NO_MAP)
  plan  --core <dir> --data <new.json>        проверить и показать план
  apply --core <dir> --data <new.json> [--base-revision N]
Выходы — JSON в stdout; коды: 0 ок, 2 ошибка валидации, 3 MAP_CONFLICT,
4 UNSUPPORTED_SCHEMA, 5 NO_MAP (для read несуществующей карты).
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MAP_NAME = "understanding-map.json"
SUPPORTED_SCHEMA = 1
ID_RE = re.compile(r"^[A-Za-z0-9А-Яа-яЁё][A-Za-z0-9А-Яа-яЁё0-9._-]{0,63}$")
REVIEW_STATES = ("draft", "changes_requested", "confirmed")
SOURCE_KINDS = ("file", "url", "doc", "chat", "other")
REQUIRED = ("schema_version", "revision", "goal", "review_state",
            "understanding", "assumptions", "gaps", "decisions",
            "sources", "next_step")
KNOWN_V1_KEYS = frozenset(REQUIRED) | {"title", "analysis_flow", "architecture"}


def _err(errors, path, msg):
    errors.append(f"{path}: {msg}")


def _check_entry(errors, path, entry, known_source_ids=None):
    if not isinstance(entry, dict):
        _err(errors, path, "ожидался объект")
        return None
    for req in ("id", "title"):
        if not isinstance(entry.get(req), str) or not entry.get(req):
            _err(errors, path, f"обязательное строковое поле '{req}'")
    if isinstance(entry.get("id"), str) and not ID_RE.fullmatch(entry["id"]):
        _err(errors, path, f"недопустимый id {entry['id']!r}")
    for opt in ("tag", "detail"):
        if opt in entry and not isinstance(entry[opt], str):
            _err(errors, path, f"поле '{opt}' должно быть строкой")
    if "source_ids" in entry:
        sids = entry["source_ids"]
        if not isinstance(sids, list):
            _err(errors, path, "source_ids должен быть списком строк")
        else:
            for j, sid in enumerate(sids):
                if not isinstance(sid, str) or not ID_RE.fullmatch(sid):
                    _err(errors, path, f"source_ids[{j}]: ожидался валидный строковый id")
                elif known_source_ids is not None and sid not in known_source_ids:
                    _err(errors, path, f"source_ids ссылается на неизвестный источник {sid!r}")
    return entry.get("id")


def validate_map(data) -> list:
    """Проверка канона v1 (зеркало schemas/understanding-map.schema.json).
    Возвращает список ошибок; пустой список — документ валиден.
    Неизвестные поля допускаются и сохраняются."""
    errors = []
    if not isinstance(data, dict):
        return ["корень: ожидался объект"]
    for req in REQUIRED:
        if req not in data:
            _err(errors, req, "обязательное поле отсутствует")
    if errors:
        return errors
    if data["schema_version"] != SUPPORTED_SCHEMA:
        _err(errors, "schema_version", f"поддерживается только {SUPPORTED_SCHEMA}")
    if not isinstance(data["revision"], int) or isinstance(data["revision"], bool) or data["revision"] < 1:
        _err(errors, "revision", "ожидалось целое >= 1")
    if not isinstance(data["goal"], str) or not data["goal"]:
        _err(errors, "goal", "ожидалась непустая строка")
    if "title" in data and not isinstance(data["title"], str):
        _err(errors, "title", "ожидалась строка")
    if data["review_state"] not in REVIEW_STATES:
        _err(errors, "review_state", f"допустимо: {', '.join(REVIEW_STATES)}")

    known_sources = set()
    if not isinstance(data["sources"], list):
        _err(errors, "sources", "ожидался список")
    else:
        for i, src in enumerate(data["sources"]):
            path = f"sources[{i}]"
            if not isinstance(src, dict):
                _err(errors, path, "ожидался объект")
                continue
            sid = src.get("id")
            if not isinstance(sid, str) or not ID_RE.fullmatch(sid or ""):
                _err(errors, path, "недопустимый или отсутствующий id")
            elif sid in known_sources:
                _err(errors, path, f"дубль id {sid!r}")
            else:
                known_sources.add(sid)
            if src.get("kind") not in SOURCE_KINDS:
                _err(errors, path, f"kind: допустимо {', '.join(SOURCE_KINDS)}")
            ref = src.get("ref")
            if not isinstance(ref, str) or not ref:
                _err(errors, path, "обязательное строковое поле 'ref'")
            elif src.get("kind") == "file":
                normalized = ref.replace("\\", "/")
                if re.match(r"^([A-Za-z]:/|/)", normalized):
                    _err(errors, path, "локальный путь должен быть относительным")
            if "locator" in src and not isinstance(src["locator"], str):
                _err(errors, path, "locator должен быть строкой")

    seen_ids = set(known_sources)
    for section in ("understanding", "assumptions", "gaps"):
        if not isinstance(data[section], list):
            _err(errors, section, "ожидался список")
            continue
        for i, entry in enumerate(data[section]):
            eid = _check_entry(errors, f"{section}[{i}]", entry, known_sources)
            if eid:
                if eid in seen_ids:
                    _err(errors, f"{section}[{i}]", f"дубль id {eid!r}")
                seen_ids.add(eid)

    if not isinstance(data["decisions"], list):
        _err(errors, "decisions", "ожидался список")
    else:
        for i, dec in enumerate(data["decisions"]):
            path = f"decisions[{i}]"
            if not isinstance(dec, dict):
                _err(errors, path, "ожидался объект")
                continue
            eid = _check_entry(errors, path, {k: dec[k] for k in dec if k != "ref"})
            if "ref" in dec and not isinstance(dec["ref"], str):
                _err(errors, path, "ref должен быть строкой")
            if eid:
                if eid in seen_ids:
                    _err(errors, path, f"дубль id {eid!r}")
                seen_ids.add(eid)

    ns = data["next_step"]
    if ns is not None:
        eid = _check_entry(errors, "next_step", ns, known_sources)
        if eid:
            if eid in seen_ids:
                _err(errors, "next_step", f"дубль id {eid!r}")
            seen_ids.add(eid)

    for section, req_field in (("analysis_flow", "title"), ("architecture", "title")):
        if section not in data:
            continue
        if not isinstance(data[section], list):
            _err(errors, section, "ожидался список")
            continue
        for i, row in enumerate(data[section]):
            if not isinstance(row, dict) or not isinstance(row.get(req_field), str) or not row.get(req_field):
                _err(errors, f"{section}[{i}]", f"обязательное строковое поле '{req_field}'")
    return errors


def map_path(core: Path) -> Path:
    return Path(core) / MAP_NAME


def read_disk(core: Path):
    """(status, data): ok | no_map | unsupported | broken."""
    p = map_path(core)
    if not p.exists():
        return "no_map", None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return "broken", str(e)
    sv = data.get("schema_version") if isinstance(data, dict) else None
    if isinstance(sv, int) and sv > SUPPORTED_SCHEMA:
        return "unsupported", data
    return "ok", data


def _emit(payload, code=0):
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return code


def _conflict_diff(disk, new):
    """Краткий diff disk ↔ incoming для MAP_CONFLICT: явный выбор — за человеком."""
    diff = {}
    for key in ("title", "goal", "review_state", "next_step"):
        if disk.get(key) != new.get(key):
            diff[key] = {"disk": disk.get(key), "incoming": new.get(key)}
    for section in ("understanding", "assumptions", "gaps", "decisions", "sources"):
        d_rows = {e.get("id"): e for e in disk.get(section) or [] if isinstance(e, dict)}
        n_rows = {e.get("id"): e for e in new.get(section) or [] if isinstance(e, dict)}
        added = sorted(str(i) for i in n_rows.keys() - d_rows.keys())
        removed = sorted(str(i) for i in d_rows.keys() - n_rows.keys())
        changed = sorted(str(i) for i in n_rows.keys() & d_rows.keys()
                         if n_rows[i] != d_rows[i])
        if added or removed or changed:
            diff[section] = {"added": added, "removed": removed, "changed": changed}
    return diff


def cmd_read(core: Path) -> int:
    status, data = read_disk(core)
    if status == "no_map":
        return _emit({"status": "NO_MAP", "path": str(map_path(core))}, 5)
    if status == "broken":
        return _emit({"status": "BROKEN_MAP", "error": data}, 2)
    if status == "unsupported":
        return _emit({"status": "UNSUPPORTED_SCHEMA", "read_only": True,
                      "schema_version": data.get("schema_version"),
                      "supported": SUPPORTED_SCHEMA, "data": data}, 4)
    return _emit({"status": "OK", "data": data})


def _prepare(core: Path, data_path: Path, base_revision):
    """Общая часть plan/apply. Возвращает (result_dict, exit_code, new_doc|None)."""
    try:
        new_doc = json.loads(Path(data_path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        return {"status": "INVALID_DATA", "errors": [str(e)]}, 2, None
    errors = validate_map(new_doc)
    if errors:
        return {"status": "INVALID_DATA", "errors": errors}, 2, None
    status, disk = read_disk(core)
    if status == "unsupported":
        return {"status": "UNSUPPORTED_SCHEMA", "read_only": True,
                "schema_version": disk.get("schema_version"),
                "supported": SUPPORTED_SCHEMA}, 4, None
    if status == "broken":
        return {"status": "BROKEN_MAP", "error": disk,
                "hint": "исправьте файл вручную или удалите его осознанно"}, 2, None
    if status == "no_map":
        new_doc["revision"] = 1
        return {"status": "READY", "action": "create", "base_revision": None,
                "new_revision": 1}, 0, new_doc
    disk_rev = disk.get("revision")
    if base_revision is None:
        return {"status": "MAP_CONFLICT", "reason": "карта уже существует — "
                "нужен --base-revision (CAS)", "disk_revision": disk_rev,
                "diff": _conflict_diff(disk, new_doc),
                "hint": "перечитайте карту, объедините ЯВНО и повторите"}, 3, None
    if disk_rev != base_revision:
        return {"status": "MAP_CONFLICT", "reason": "ревизия на диске изменилась",
                "disk_revision": disk_rev, "base_revision": base_revision,
                "diff": _conflict_diff(disk, new_doc),
                "hint": "перечитайте карту, объедините ЯВНО и повторите"}, 3, None
    # rule (б): неизвестные будущие поля disk-документа, которые вход не
    # переопределил, переносятся при read-modify-write, а не теряются.
    for key, value in disk.items():
        if key not in KNOWN_V1_KEYS and key not in new_doc:
            new_doc[key] = value
    new_doc["revision"] = base_revision + 1
    return {"status": "READY", "action": "update", "base_revision": base_revision,
            "new_revision": base_revision + 1}, 0, new_doc


def cmd_plan(core: Path, data_path: Path, base_revision) -> int:
    result, code, new_doc = _prepare(core, data_path, base_revision)
    if new_doc is not None:
        result["counts"] = {k: len(new_doc.get(k) or []) for k in
                            ("understanding", "assumptions", "gaps",
                             "decisions", "sources")}
        result["review_state"] = new_doc["review_state"]
        result["dry_run"] = True
    return _emit(result, code)


def cmd_apply(core: Path, data_path: Path, base_revision) -> int:
    # Быстрая проверка входа без лока: ошибки валидации не требуют блокировки.
    result, code, _ = _prepare(core, data_path, base_revision)
    if code != 0:
        return _emit(result, code)
    target = map_path(core)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Межпроцессная блокировка: эксклюзивное создание lock-файла; проверка
    # ревизии повторяется ПОД локом — окно check→replace закрыто.
    lock = target.with_name(MAP_NAME + ".lock-map-store")
    try:
        lock_fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return _emit({"status": "MAP_CONFLICT",
                      "reason": "карта заблокирована другим writer",
                      "lock": str(lock),
                      "hint": "дождитесь завершения; осиротевший lock "
                              "удаляется вручную осознанно"}, 3)
    try:
        os.close(lock_fd)
        result, code, new_doc = _prepare(core, data_path, base_revision)
        if code != 0:
            return _emit(result, code)
        if result["action"] == "update":
            backup = target.with_name(f"{MAP_NAME}.bak-rev{result['base_revision']}")
            if not backup.exists():
                backup.write_bytes(target.read_bytes())
            result["backup"] = str(backup)
        tmp = target.with_name(f"{target.name}.tmp-map-store-{os.getpid()}")
        try:
            tmp.write_text(json.dumps(new_doc, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8", newline="\n")
            os.replace(tmp, target)
        finally:
            tmp.unlink(missing_ok=True)
    finally:
        lock.unlink(missing_ok=True)
    result["status"] = "APPLIED"
    result["path"] = str(target)
    return _emit(result, 0)


def main() -> int:
    ap = argparse.ArgumentParser(description="Канон карты понимания в ядре проекта.")
    ap.add_argument("command", choices=["read", "plan", "apply"])
    ap.add_argument("--core", required=True, help="каталог выбранного ядра проекта")
    ap.add_argument("--data", help="JSON с новым содержимым карты (plan/apply)")
    ap.add_argument("--base-revision", type=int, default=None,
                    help="ревизия, от которой сделаны правки (CAS; обязательна при update)")
    args = ap.parse_args()
    core = Path(args.core)
    if not core.is_dir():
        return _emit({"status": "INVALID_DATA",
                      "errors": [f"ядро не найдено: {core}"]}, 2)
    if args.command == "read":
        return cmd_read(core)
    if not args.data:
        return _emit({"status": "INVALID_DATA",
                      "errors": ["--data обязателен для plan/apply"]}, 2)
    if args.command == "plan":
        return cmd_plan(core, Path(args.data), args.base_revision)
    return cmd_apply(core, Path(args.data), args.base_revision)


if __name__ == "__main__":
    sys.exit(main())
