---
description: Односторонне обновить LLM-base с hub на consumer и проверить target Claude/Codex/OpenCode. Ничего не отправляет с consumer.
allowed-tools: Bash, Read, AskUserQuestion
---

# /sync-base

Обнови исходный build-репозиторий и проверь target-пакеты. Команда не ставит
MCP/plugins, не выбирает модель и не отправляет feedback, session reports или
телеметрию.

## Правила

- Поток только `hub → consumer`.
- Маркер `.developer-marker` в корне build-репозитория означает hub.
- Consumer получает `origin push URL = NO_PUSH_CONSUMER`.
- Эта команда никогда не выполняет `git push`, даже на hub.
- Auth/environment не читать и не копировать.
- При конфликте pull остановиться; не делать reset/checkout без отдельного
  подтверждения и бэкапа.
- Полный build-репозиторий нельзя считать token-safe client home.

## Алгоритм

1. Определи корень репозитория по расположению этой команды; для legacy clone
   допускается `~/.claude`, но в отчёте пометь его как ожидающий миграции.
2. Определи роль:

   ```powershell
   $Role = if (Test-Path "$Repo\.developer-marker") { 'hub' } else { 'consumer' }
   if ($Role -eq 'consumer') {
     git -C "$Repo" remote set-url --push origin NO_PUSH_CONSUMER
   }
   ```

3. Выполни только fetch/pull:

   ```powershell
   git -C "$Repo" -c http.proxy="" -c https.proxy="" fetch origin main
   git -C "$Repo" -c http.proxy="" -c https.proxy="" pull --rebase --autostash origin main
   ```

4. Запусти детерминированную проверку:

   ```powershell
   python "$Repo\scripts\base_cli.py" verify
   ```

5. Для каждого установленного target с `.base\target-manifest.json` выполни
   doctor:

   ```powershell
   python "$Repo\scripts\base_cli.py" doctor --target claude --home "$HOME"
   python "$Repo\scripts\base_cli.py" doctor --target codex --home "$HOME"
   python "$Repo\scripts\base_cli.py" doctor --target opencode --home "$HOME"
   ```

   Отсутствующий target — `NOT_INSTALLED`, не ошибка. Drift не перезаписывать
   напрямую: применить только утверждённый target-bound Foundation package
   через его `plan`/`install`.

6. Если утверждённого immutable rendered package ещё нет, явно вывести
   `BLOCKED_APPROVED_FOUNDATION_SOURCE`. Не подменять его raw render и не
   заявлять, что consumer уже получил полное снижение контекста.

## Итог

```text
role: hub|consumer
source: updated|clean|conflict
outbound: disabled|hub-explicit-only
context-budget: PASS|FAIL
claude: HEALTHY|DRIFT|NOT_INSTALLED
codex: HEALTHY|DRIFT|NOT_INSTALLED
opencode: HEALTHY|DRIFT|NOT_INSTALLED
foundation: READY|BLOCKED_APPROVED_FOUNDATION_SOURCE
```
