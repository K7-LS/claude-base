# LLM Base

Канонический build-репозиторий общей базы для трёх нативных клиентов:
Claude, Codex и OpenCode.

Это не готовый client home. Прямой clone всего репозитория в `~/.claude`,
`~/.codex` или OpenCode config-dir снова откроет большой каталог для discovery
и не считается token-safe установкой. Consumer получает только target-bound
рендер через прошедший приёмку Foundation package.

Kimi не является отдельным target. При необходимости это лишь одна из моделей,
которую пользователь может выбрать через провайдера OpenCode. База не задаёт
провайдера, модель или платный fallback.

## Архитектура

| Слой | Назначение |
|---|---|
| `core/AGENTS.core.md` | Компактные общие правила без названий vendor-инструментов. |
| `targets/claude/` | Нативные правила и agent format Claude. |
| `targets/codex/` | Нативные `AGENTS.md` и TOML agents Codex. |
| `targets/opencode/` | Нативные правила, `opencode.json`, agents и безопасный launcher. |
| `agents/`, `skills/` | Build-каталог; не активируется целиком. |
| `base-manifest.json` | Ровно три target, явный active set, one-way sync и secret policy. |
| `context-budget.json` | Детерминированные лимиты стартового контекста. |
| `scripts/base_cli.py` | Render, context audit, doctor и безопасный transcript usage audit. |

Сейчас в каждом target активен только компактный read-only `auditor`; active
skills пусты. Остальной каталог сохраняется как исходник для осознанной
приёмки, но не должен автоматически попадать в prompt/discovery.

## Проверка и рендер

```powershell
python .\scripts\base_cli.py verify
python .\scripts\base_cli.py render --target claude --output .\out\claude
python .\scripts\base_cli.py render --target codex --output .\out\codex
python .\scripts\base_cli.py render --target opencode --output .\out\opencode
python .\scripts\base_cli.py doctor --target opencode --home .\fake-home
python .\scripts\base_cli.py audit-transcript .\session.jsonl
```

Рендер работает офлайн, не выполняет login/network, не выбирает модель и не
копирует auth/environment. OpenCode launcher отключает импорт Claude Code
prompt/skills, чтобы два target не смешивались.

## Контекст и токены

`context-budget.json` проверяет отдельно vendor-neutral core, target-layer,
видимый active catalog и общий startup budget. Простой диалог не должен сам
запускать tools, subagents или reviewer.

`audit-transcript` агрегирует usage без вывода prompt, команд, raw identifiers
или секретов. Он различает input, output и provider cache semantics и
дедуплицирует повторённые usage-записи. Фактический разбор инцидента находится
в `docs/audits/2026-07-26-token-account-risk.md`.

Важно: счётчик «processed/cache tokens» не равен размеру одного prompt. Большая
история и tool loop повторно обрабатываются на каждом model turn, поэтому одна
пользовательская реплика может породить много дорогих внутренних запросов.

## Односторонняя синхронизация

Поток только `hub → consumer`:

- hub публикует проверенные изменения отдельным действием;
- consumer только получает обновления;
- consumer Git push URL заменяется на `NO_PUSH_CONSUMER`;
- feedback, session reports и телеметрия с consumer не загружаются;
- auth и environment никогда не входят в базу.

`scripts/auto-push.ps1` на consumer — явный локальный no-op. Старые скрипты
обратного сбора, скачивания feedback и настройки write-token удалены.

## Инсталлер

`claude-lite-instaler` в прежнем виде — legacy и не должен клонировать весь
build-репозиторий в client home. Новая ветка Foundation installer поддерживает
target-bound пакеты Claude/Codex/OpenCode, раздельное состояние и строгий
one-way manifest contract.

Полный employee release остаётся fail-closed до утверждённого immutable
rendered source, frozen component evidence, fake-home acceptance, независимого
аудита и отдельно разрешённого canary. Synthetic PASS не равен release PASS.

## Безопасность

В git не должны попадать credentials, auth stores, environment, история чатов,
projects, cache, downloads, plugins, backups, file-history, `_sandbox` и
`.developer-marker`. Диагностика должна быть bounded и redacted.
