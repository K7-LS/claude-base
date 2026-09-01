# -*- coding: utf-8 -*-
"""Доставка пакета Codex через CLI обязана попадать в журнал моста.

Дефект (2026-08-28): MCP-канал терял тред («Session not found»), доставка шла
фолбэком `codex exec resume`, но PostToolUse-хук видит только MCP-вызовы —
в журнале оставались одни красные ошибки, а состоявшийся обмен пропадал.
"""
import json
import pathlib
import subprocess
import sys

import pytest

SCRIPTS = pathlib.Path.home() / ".claude" / "scripts"
sys.path.insert(0, str(SCRIPTS))

import codex_deliver  # noqa: E402


def _rollout(path: pathlib.Path, thread: str, rows: list) -> pathlib.Path:
    target = path / f"rollout-2026-08-28T13-07-22-{thread}.jsonl"
    target.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return target


THREAD = "01a047d6-8b9f-72b2-9f30-fc3cd600f21b"


def test_final_answer_is_taken_from_task_complete(tmp_path):
    path = _rollout(tmp_path, THREAD, [
        {"type": "event_msg", "payload": {"type": "agent_message",
                                          "message": "промежуточное"}},
        {"type": "event_msg", "payload": {"type": "task_complete",
                                          "last_agent_message": "финальный вердикт"}},
        {"type": "response_item", "payload": {"type": "прочее"}},
    ])
    assert codex_deliver.answer_from_rollout(path) == "финальный вердикт"


def test_agent_message_is_used_when_task_did_not_complete(tmp_path):
    path = _rollout(tmp_path, THREAD, [
        {"type": "event_msg", "payload": {"type": "agent_message",
                                          "message": "единственное сообщение"}},
    ])
    assert codex_deliver.answer_from_rollout(path) == "единственное сообщение"


def test_broken_and_missing_rollout_do_not_raise(tmp_path):
    broken = tmp_path / "rollout-2026-08-28T13-07-22-broken.jsonl"
    broken.write_text("не json\n{\n", encoding="utf-8")
    assert codex_deliver.answer_from_rollout(broken) == ""
    assert codex_deliver.answer_from_rollout(None) == ""
    assert codex_deliver.answer_from_rollout(tmp_path / "нет.jsonl") == ""


def test_thread_id_is_recovered_from_rollout_name(tmp_path):
    path = _rollout(tmp_path, THREAD, [])
    assert codex_deliver.thread_from_rollout(path) == THREAD


def test_rollout_lookup_prefers_the_requested_thread(tmp_path, monkeypatch):
    other = _rollout(tmp_path, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", [])
    wanted = _rollout(tmp_path, THREAD, [])
    # чужой тред новее — выбор всё равно по идентификатору, не по времени
    import os
    import time
    os.utime(other, (time.time() + 10, time.time() + 10))
    monkeypatch.setattr(codex_deliver, "SESSIONS", tmp_path)
    assert codex_deliver.rollout_for(THREAD) == wanted
    assert codex_deliver.rollout_for("") == other      # без треда — самый свежий


def test_delivery_is_written_to_the_bridge_journal(tmp_path, monkeypatch):
    journal = tmp_path / "dialog.md"
    script = (
        "import json,sys,pathlib\n"
        "sys.stdin.reconfigure(encoding='utf-8')\n"
        "d=json.load(sys.stdin)\n"
        f"pathlib.Path(r'{journal}').write_text("
        "json.dumps(d, ensure_ascii=False), encoding='utf-8')\n"
    )
    fake_tool = tmp_path / "fake_journal.py"
    fake_tool.write_text(script, encoding="utf-8")
    monkeypatch.setattr(codex_deliver, "JOURNAL_TOOL", fake_tool)

    assert codex_deliver.journal("claude", "текст пакета", "ответ Codex", THREAD)
    written = json.loads(journal.read_text(encoding="utf-8"))
    assert written["direction"] == "claude"
    assert written["prompt"] == "текст пакета"
    assert written["answer"] == "ответ Codex"
    assert written["channel"] == "через CLI codex exec"
    assert "resume" in written["tool"]


def test_empty_answer_is_recorded_explicitly(tmp_path, monkeypatch):
    journal = tmp_path / "dialog.md"
    fake_tool = tmp_path / "fake_journal.py"
    fake_tool.write_text(
        "import json,sys,pathlib\n"
        "sys.stdin.reconfigure(encoding='utf-8')\n"
        f"pathlib.Path(r'{journal}').write_text("
        "json.dumps(json.load(sys.stdin), ensure_ascii=False), encoding='utf-8')\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(codex_deliver, "JOURNAL_TOOL", fake_tool)
    assert codex_deliver.journal("claude", "пакет", "", "")
    written = json.loads(journal.read_text(encoding="utf-8"))
    assert "ответ пуст" in written["answer"]


def test_journal_failure_does_not_break_delivery(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_deliver, "JOURNAL_TOOL", tmp_path / "нет-такого.py")
    assert codex_deliver.journal("claude", "пакет", "ответ", "") is False


def test_manual_mode_labels_the_cli_channel(tmp_path, monkeypatch):
    # interop_journal сам должен проставлять метку канала из payload
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("HOME", str(tmp_path))
    payload = {
        "direction": "claude",
        "tool": "codex exec resume",
        "prompt": "пакет",
        "answer": "ответ",
        "channel": "через CLI codex exec",
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "interop_journal.py"), "--manual"],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    written = (tmp_path / ".claude" / "interop" / "dialog.md").read_text(
        encoding="utf-8"
    )
    assert "через CLI codex exec" in written
    assert "восстановлено из rollout" not in written
    assert "Claude → Codex" in written


def test_resume_command_omits_cd_and_new_thread_keeps_it(monkeypatch, tmp_path):
    # codex exec resume принимает только --config: с --cd CLI падает
    # «unexpected argument», а доставка выглядела успешной, потому что из
    # rollout поднимался предыдущий ответ.
    import codex_deliver as cd

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command

        class R:
            returncode = 0
            stdout = b""
            stderr = b""
        return R()

    monkeypatch.setattr(cd.subprocess, "run", fake_run)
    monkeypatch.setattr(cd, "find_codex", lambda: "codex.exe")
    monkeypatch.setattr(cd, "SESSIONS", tmp_path)
    monkeypatch.setattr(cd, "journal", lambda *a, **k: True)
    prompt = tmp_path / "p.txt"
    prompt.write_text("пакет", encoding="utf-8")

    monkeypatch.setattr(
        sys, "argv",
        ["codex_deliver.py", "--thread", THREAD, "--prompt-file", str(prompt)],
    )
    cd.main()
    resume_cmd = captured["command"]
    assert resume_cmd[1:3] == ["exec", "resume"]
    assert "--cd" not in resume_cmd
    assert THREAD in resume_cmd

    monkeypatch.setattr(
        sys, "argv", ["codex_deliver.py", "--prompt-file", str(prompt)]
    )
    cd.main()
    assert "--cd" in captured["command"]      # новый тред задаёт рабочую папку


def test_previous_answer_is_not_reported_as_delivered(monkeypatch, tmp_path, capsys):
    # Ответ засчитывается только если task_complete прибавился после доставки.
    import codex_deliver as cd

    rollout = _rollout(tmp_path, THREAD, [
        {"type": "event_msg", "payload": {"type": "task_complete",
                                          "last_agent_message": "старый ответ"}},
    ])
    assert cd.completed_answers(rollout) == 1

    def fake_run(command, **kwargs):
        class R:
            returncode = 2
            stdout = b""
            stderr = b"error: unexpected argument '--cd' found"
        return R()

    monkeypatch.setattr(cd.subprocess, "run", fake_run)
    monkeypatch.setattr(cd, "find_codex", lambda: "codex.exe")
    monkeypatch.setattr(cd, "SESSIONS", tmp_path)
    monkeypatch.setattr(cd, "journal", lambda *a, **k: True)
    prompt = tmp_path / "p.txt"
    prompt.write_text("пакет", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv",
        ["codex_deliver.py", "--thread", THREAD, "--prompt-file", str(prompt)],
    )
    assert cd.main() == 1
    report = json.loads(capsys.readouterr().out.split("\n--- ")[0])
    assert report["status"] == "NO_NEW_ANSWER"
    assert "старый ответ" not in json.dumps(report, ensure_ascii=False)
