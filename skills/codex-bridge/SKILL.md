---
name: codex-bridge
description: Use when нужно поднять мост Claude↔Codex, проверить связь между ними или открыть живой просмотр их переписки.
---

# Мост Claude ↔ Codex

Соединение уже прописано с обеих сторон (`codex` MCP у Claude, `claude` MCP у
Codex) — «поднимать» нужно только просмотр и проверку.

## Поднять просмотр

1. Запусти фоном `python ~/.claude/scripts/interop_chat_server.py`. Если сервер
   уже работает, скрипт скажет об этом и выйдет без ошибки.
2. Страница: http://127.0.0.1:7343 — чат с автообновлением каждые 2 секунды и
   моделями сторон. Владельцу без сессии — двойной клик
   `~/.claude/interop/Мост-чат.bat`.

## Проверить связь

- Claude → Codex: вызови `mcp__codex__codex` с коротким пингом (sandbox
  `read-only`, approval-policy `never`); диалог продолжается через
  `mcp__codex__codex-reply` по `threadId`.
- Codex → Claude: `codex exec "Вызови MCP-инструмент Read сервера claude с
  file_path = <мелкий файл>"` — на стороне Codex инструменты Claude называются
  `mcp__claude__<Tool>` и добираются через ToolSearch.
- Обе проверки должны появиться в `~/.claude/interop/dialog.md` — его пишут
  PostToolUse-хуки: у Claude в `settings.shared.json` (ключ `hooks`
  strictly-shared), у Codex в `~/.codex/hooks.json`.

## Грабли

- Codex, порождённый мостом, не видит ни одного MCP-сервера — рекурсия отрезана,
  это норма, а не поломка.
- `codex exec --sandbox read-only` отменяет MCP-вызовы («user cancelled MCP tool
  call»); штатный режим Codex их пропускает.
- Модель Codex может ложно ответить «MCP-серверов нет» — верь только реальному
  вызову инструмента.
- После любой правки `~/.codex/hooks.json` Codex молча отключает ВСЕ свои хуки,
  пока владелец не подтвердит доверие в интерактивном Codex.
- Мостовые треды Codex — headless: в списке чатов его приложения их нет; открыть
  можно `codex resume <threadId>` (threadId есть в журнале).
- Очистка ленты — удалить `interop/dialog.md`; сервер и страница это переживут.
