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
  `mcp__codex__codex-reply` по `threadId`. Нужен его shell (чтение файлов,
  логов, `codex_sync check`) — sandbox `danger-full-access` с явным запретом
  записи в промпте: read-only sandbox на DANIIL-LAPTOP сломан (см. грабли).
- Codex → Claude: `codex exec "Вызови MCP-инструмент Read сервера claude с
  file_path = <мелкий файл>"` — на стороне Codex инструменты Claude называются
  `mcp__claude__<Tool>` и добираются через ToolSearch.
- Обе проверки должны появиться в `~/.claude/interop/dialog.md` — его пишут
  PostToolUse-хуки: у Claude в `settings.shared.json` (ключ `hooks`
  strictly-shared), у Codex в `~/.codex/hooks.json`.

## Длинные запросы — только фоном

Содержательный запрос (ревью, пакет решений) Codex на high-режиме думает
5–15 минут. Синхронный вызов `mcp__codex__codex` на это время замораживает
сессию и выглядит зависанием. Правило: всё длиннее пинга отправляй через
фонового агента (Agent → general-purpose, внутри — ToolSearch
`select:mcp__codex__codex` и сам вызов); владельцу скажи, что ответ появится
в журнале. Решения по среде Codex вообще не принимай сам — отправляй ему
пакетом вопросов, исполняй его вердикты (поручение владельца 2026-08-26).

## Грабли

- **Мост-в-мосте виснет намертво**: если мостовая сессия Codex вызывает
  инструменты сервера `claude` (`mcp__claude__*`), вложенный `claude mcp serve`
  деадлочится без ошибки. Каждый вызов `mcp__codex__codex` делай с
  `config: {"mcp_servers.claude.enabled": false}` и в промпте запрещай
  mcp__claude__*, файлы — его собственным shell. Диагностика зависания:
  свежий rollout в `~/.codex/sessions/<дата>/` перестал расти ≥2 минут.
- Кириллические сегменты глубоких путей в его node_repl-логах превращаются в
  мохибейк — рабочие папки для Codex давай через ASCII-junction.
- Мостовая сессия с записью файлов — sandbox `danger-full-access` (его же
  штатный режим из config.toml): `workspace-write` на Windows валит его shell
  ошибкой `CreateProcessWithLogonW failed: 267` на junction/Я.Диске.
  Чистые вопросы модели без shell — по-прежнему `read-only`.
- **Read-only sandbox не запускает shell (2026-09-03, решение владельца —
  идти через `danger-full-access`).** Managed-копия
  `~/.llm-foundation/clients/codex-cli/bin/codex.exe` лежит отдельно от
  `codex-resources`, поэтому `codex-windows-sandbox-setup.exe: program not
  found`; MCP `codex` у Claude перерегистрирован на комплектный
  `…/codex-cli/codex-home/packages/standalone/current/bin/codex.exe`
  (бэкап `~/.claude.json.bak-codex-mcp-20260903`). С ним помощник
  находится, но `CreateProcessAsUserW failed: 5` — задача на стороне Codex;
  упаковка managed-копии — дефект инсталлятора (в плане переработки).
- **Потолок вызова ~30 минут**: codex mcp-server не стримит прогресс, и клиент
  рубит вызов по idle-таймауту (дефолт 1800 с; в базе поднят env
  `MCP_TOOL_TIMEOUT=7200000`). Пакеты крои под ~20 минут работы Codex.
  Если вызов оборвался — НЕ перезапускай задачу вслепую: сначала проверь
  свежий rollout в `~/.codex/sessions/<дата>/` — работа часто уже доведена
  до конца (`task_complete`), финальный ответ извлекается оттуда, а тред
  продолжается `codex-reply` по threadId рабочей сессии.
- `codex exec --sandbox read-only` отменяет MCP-вызовы («user cancelled MCP tool
  call»); штатный режим Codex их пропускает.
- **`codex-reply` теряет тред после рестарта MCP-сервера** («Session not found»,
  хотя rollout цел — сессии живут в памяти сервера). НЕ повторяй MCP-вызов:
  доставь тем же пакетом через доставщик, он же пишет обмен в журнал —
  `python ~/.claude/scripts/codex_deliver.py --thread <threadId>
  --prompt-file <пакет.txt>` (проверено 2026-08-28, дважды).
- **Журнал видит только MCP-канал.** PostToolUse-хук ловит вызовы
  `mcp__codex__*`; запуск `codex exec` — обычный процесс, хук его не видит.
  Прямой `codex exec` оставляет в дашборде только красные ошибки MCP, а
  состоявшийся обмен пропадает. Поэтому CLI-доставку делай ТОЛЬКО через
  `codex_deliver.py`: он берёт финальный ответ из rollout
  (`task_complete.last_agent_message`) и пишет обе стороны с меткой
  «через CLI codex exec».
- Модель Codex может ложно ответить «MCP-серверов нет» — верь только реальному
  вызову инструмента.
- После любой правки `~/.codex/hooks.json` Codex молча отключает ВСЕ свои хуки,
  пока владелец не подтвердит доверие в интерактивном Codex.
- Мостовые треды Codex — headless: в списке чатов его приложения их нет; открыть
  можно `codex resume <threadId>` (threadId есть в журнале).
- Очистка ленты — удалить `interop/dialog.md`; сервер и страница это переживут.
