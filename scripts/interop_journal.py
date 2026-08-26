# -*- coding: utf-8 -*-
"""Журнал переговоров Claude↔Codex: ~/.claude/interop/dialog.md.

Вызывается PostToolUse-хуком (stdin — JSON события):
  Claude Code: python interop_journal.py --source claude
  Codex:       python interop_journal.py --source codex

Никогда не роняет вызвавший инструмент: любая ошибка — тихий exit 0.
"""
import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

JOURNAL = Path.home() / ".claude" / "interop" / "dialog.md"
LIMIT = 4000  # символов на реплику; журнал — для чтения человеком


def clip(text: str) -> str:
    text = (text or "").strip()
    if len(text) > LIMIT:
        return text[:LIMIT] + "\n… [обрезано, полный текст в транскрипте сессии]"
    return text


def extract_text(value) -> str:
    """Достаёт человекочитаемый текст из типовых форм tool_response."""
    if value is None:
        return ""
    if isinstance(value, str):
        # Внутри может лежать JSON вида {"threadId": ..., "content": ...}
        try:
            inner = json.loads(value)
        except ValueError:
            return value
        return extract_text(inner)
    if isinstance(value, list):
        return "\n".join(filter(None, (extract_text(v) for v in value)))
    if isinstance(value, dict):
        for key in ("content", "text", "message", "result", "output"):
            if key in value:
                return extract_text(value[key])
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def claude_model_from_transcript(path: str) -> str:
    """Модель текущей сессии Claude: последний "model" в хвосте транскрипта."""
    try:
        p = Path(path)
        with open(p, "rb") as f:
            f.seek(max(0, p.stat().st_size - 262144))
            tail = f.read().decode("utf-8", "replace")
        for m in reversed(re.findall(r'"model"\s*:\s*"([^"]+)"', tail)):
            if not m.startswith("<"):  # пропустить служебные маркеры вида <synthetic>
                return m
    except OSError:
        pass
    return ""


def codex_default_model() -> str:
    """Модель Codex по умолчанию из ~/.codex/config.toml (верхний уровень)."""
    try:
        text = (Path.home() / ".codex" / "config.toml").read_text(encoding="utf-8")
        m = re.search(r'^model\s*=\s*"([^"]+)"', text, re.M)
        return m.group(1) if m else ""
    except OSError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["claude", "codex"], default="claude")
    args = parser.parse_args()

    # Windows по умолчанию декодирует stdin в cp1251 — событие приходит в UTF-8
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    event = json.load(sys.stdin)
    tool = event.get("tool_name") or event.get("tool") or "?"
    tool_input = event.get("tool_input") or event.get("arguments") or {}
    tool_response = event.get("tool_response") or event.get("result")

    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    if args.source == "claude":
        # Claude вызвал Codex через MCP-мост
        prompt = tool_input.get("prompt", "") if isinstance(tool_input, dict) else str(tool_input)
        thread = ""
        answer = extract_text(tool_response)
        try:
            meta = json.loads(answer) if answer.lstrip().startswith("{") else {}
        except ValueError:
            meta = {}
        if isinstance(meta, dict) and meta.get("threadId"):
            thread = f", тред {meta['threadId'][:13]}…"
            answer = extract_text(meta.get("content", answer))
        lines.append(f"## {stamp} — Claude → Codex ({tool}{thread})")
        my_model = claude_model_from_transcript(event.get("transcript_path", ""))
        cx_model = (tool_input.get("model") if isinstance(tool_input, dict) else "") or codex_default_model()
        lines.append(f"модели: {my_model or '?'} → {cx_model or '?'}")
        lines.append(clip(prompt))
        lines.append("")
        lines.append("**Codex ответил:**")
        lines.append(clip(answer))
    else:
        # Codex вызвал инструмент Claude через сервер claude
        lines.append(f"## {stamp} — Codex → Claude ({tool})")
        if event.get("model"):
            lines.append(f"модель: {event['model']}")
        lines.append("**Запрос:**")
        lines.append(clip(json.dumps(tool_input, ensure_ascii=False)
                          if not isinstance(tool_input, str) else tool_input))
        lines.append("")
        lines.append("**Claude вернул:**")
        lines.append(clip(extract_text(tool_response)))
    lines.append("")

    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with open(JOURNAL, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # журнал не должен ломать основной инструмент
