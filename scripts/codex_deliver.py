# -*- coding: utf-8 -*-
"""Доставка пакета Codex через CLI с обязательной записью в журнал моста.

Зачем: MCP-канал (`mcp__codex__codex-reply`) теряет тред после рестарта
сервера («Session not found»), и доставка идёт фолбэком `codex exec resume`.
Запуск процесса не является вызовом MCP-инструмента, поэтому PostToolUse-хук
его не видит: в журнале оставались только красные ошибки MCP, а состоявшийся
обмен пропадал. Этот скрипт закрывает пробел — он и доставляет, и пишет обе
стороны в ~/.claude/interop/dialog.md.

Запуск (пакет из файла либо со stdin):
    python codex_deliver.py --thread <threadId> --prompt-file пакет.txt
    echo "текст" | python codex_deliver.py --thread <threadId>
    python codex_deliver.py --prompt-file пакет.txt      # новый тред

Права администратора не требуются: только пользовательские пути и codex CLI.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
JOURNAL_TOOL = HOME / ".claude" / "scripts" / "interop_journal.py"
SESSIONS = HOME / ".codex" / "sessions"
# Мост-в-мосте деадлочится: вложенная сессия Codex не должна звать сервер claude.
NESTED_BRIDGE_OFF = ["-c", "mcp_servers.claude.enabled=false"]


def find_codex() -> str:
    found = shutil.which("codex")
    if found:
        return found
    for candidate in (
        HOME / "AppData" / "Local" / "Microsoft" / "WindowsApps" / "codex.exe",
        HOME / ".local" / "bin" / "codex.exe",
        HOME / "AppData" / "Roaming" / "npm" / "codex.cmd",
    ):
        if candidate.is_file():
            return str(candidate)
    raise SystemExit("codex CLI не найден в PATH и типовых пользовательских путях")


def rollout_for(thread: str):
    """Свежий rollout треда (или самый свежий вообще, если тред не задан)."""
    if not SESSIONS.is_dir():
        return None
    files = sorted(
        SESSIONS.rglob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if thread:
        for path in files:
            if thread in path.name:
                return path
        return None
    return files[0] if files else None


def answer_from_rollout(path) -> str:
    """Финальный ответ агента: last_agent_message из task_complete."""
    if path is None or not path.is_file():
        return ""
    answer = ""
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("type") != "event_msg":
            continue
        payload = row.get("payload") or {}
        if payload.get("type") == "task_complete":
            answer = str(payload.get("last_agent_message") or "") or answer
        elif payload.get("type") == "agent_message" and not answer:
            answer = str(payload.get("message") or "")
    return answer.strip()


def thread_from_rollout(path) -> str:
    if path is None:
        return ""
    stem = path.stem            # rollout-<дата>-<uuid>
    parts = stem.split("-")
    return "-".join(parts[-5:]) if len(parts) >= 5 else ""


def journal(direction: str, prompt: str, answer: str, thread: str) -> bool:
    """Запись обмена в журнал моста. Не роняет доставку при сбое."""
    payload = {
        "direction": direction,
        "tool": f"codex exec{' resume' if thread else ''}",
        "prompt": prompt,
        "answer": answer or "(ответ пуст: проверьте rollout)",
        "channel": "через CLI codex exec",
    }
    try:
        result = subprocess.run(
            [sys.executable, str(JOURNAL_TOOL), "--manual"],
            input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            capture_output=True,
            check=False,
            timeout=60,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Доставка пакета Codex через CLI с записью в журнал моста."
    )
    parser.add_argument("--thread", default="", help="threadId; без него — новый тред")
    parser.add_argument("--prompt-file", help="файл с текстом пакета (иначе stdin)")
    parser.add_argument("--cd", default=str(HOME / ".claude"),
                        help="рабочая папка сессии Codex")
    parser.add_argument("--timeout", type=int, default=2400,
                        help="секунд на ответ (по умолчанию 40 минут)")
    parser.add_argument("--no-journal", action="store_true",
                        help="не писать в журнал (диагностика)")
    arguments = parser.parse_args()

    if arguments.prompt_file:
        prompt = Path(arguments.prompt_file).read_text(encoding="utf-8")
    else:
        prompt = sys.stdin.buffer.read().decode("utf-8", "replace")
    prompt = prompt.strip()
    if not prompt:
        raise SystemExit("пустой пакет: нечего доставлять")

    codex = find_codex()
    command = [codex, "exec"]
    if arguments.thread:
        command += ["resume", arguments.thread]
    command += NESTED_BRIDGE_OFF + ["--cd", arguments.cd, prompt]

    before = rollout_for(arguments.thread)
    completed = subprocess.run(
        command,
        capture_output=True,
        check=False,
        timeout=arguments.timeout,
        # Без закрытого stdin codex exec не завершается после ответа и висит
        # до внешнего таймаута (проверено живьём: ответ был за секунды,
        # процесс держался десять минут).
        stdin=subprocess.DEVNULL,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    stdout = completed.stdout.decode("utf-8", "replace")
    stderr = completed.stderr.decode("utf-8", "replace")

    # Ответ берём из rollout: stdout CLI несёт служебный шум и обрезается.
    path = rollout_for(arguments.thread) or before
    answer = answer_from_rollout(path)
    thread = arguments.thread or thread_from_rollout(path)

    written = False
    if not arguments.no_journal:
        written = journal("claude", prompt, answer, arguments.thread)

    print(json.dumps({
        "status": "DELIVERED" if answer else "NO_ANSWER",
        "exit_code": completed.returncode,
        "thread": thread,
        "journaled": written,
        "rollout": str(path) if path else "",
        "stderr_tail": stderr.strip()[-400:],
    }, ensure_ascii=False, indent=2))
    if answer:
        print("\n--- ОТВЕТ CODEX ---\n")
        print(answer)
    return 0 if answer else 1


if __name__ == "__main__":
    sys.exit(main())
