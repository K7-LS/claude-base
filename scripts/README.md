# scripts

Build, audit и role-aware sync для LLM-base.

## Основные команды

- `base_cli.py` — render/audit-context/doctor/verify/audit-transcript для
  Claude, Codex и OpenCode.
- `token_audit.py` — безопасная агрегация JSONL usage без prompt и raw IDs.
- `auto-pull.ps1` — pull текущего build-репозитория; на consumer выключает
  origin push URL.
- `auto-push.ps1` — hub-only публикация whitelisted source paths; на consumer
  завершается до Git/network операций.
- `Update-ClaudeBase.ps1` — legacy/bootstrap updater; работает от собственного
  repository root, а не от жёстко заданного home.
- `codex_sync.py` — legacy Codex migration layer с manifest-controlled active
  set. Новый package собирается через `base_cli.py`.

## Важная граница

Полный build-репозиторий нельзя считать target home. Его `agents/` и `skills/`
— каталог исходников. Token-safe consumer получает только target-bound render
через утверждённый Foundation package.

Shared Claude hooks сохраняются для hub и legacy migration. Они не являются
доказательством, что новый target package автоматически установлен на
consumer. Без immutable approved package `/sync-base` обязан вернуть
`BLOCKED_APPROVED_FOUNDATION_SOURCE`.

## One-way contract

- `.developer-marker` в repository root: hub.
- Без маркера: consumer.
- Consumer: `NO_PUSH_CONSUMER`, no feedback/session/telemetry upload.
- Hub: публикация только после проверок; `/sync-base` сам push не делает.
- Credentials, auth stores и environment не являются managed source.

## Ручной запуск

```powershell
$Repo = 'C:\path\to\llm-base'
& "$Repo\scripts\auto-pull.ps1"
python "$Repo\scripts\base_cli.py" verify
```

`auto-push.ps1` вручную запускать только в явно помеченном hub repository.
