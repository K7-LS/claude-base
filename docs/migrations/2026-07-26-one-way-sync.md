# Миграция на hub → consumer

## Новый контракт

- Hub определяется только маркером `.developer-marker` в корне build-репозитория
  (путь `~/.claude` допустим лишь для legacy clone до миграции).
- Consumer выполняет pull и никогда не выполняет outbound SessionEnd.
- На consumer `origin` push URL равен `NO_PUSH_CONSUMER`.
- Consumer не получает write-credential к GitHub.
- История, отчёты, telemetry и локальные предложения не отправляются.

## Hub

1. Сохранить `.developer-marker` в корне build-репозитория.
2. Проверить fetch/push URL:

   ```powershell
   git -C "$Repo" remote get-url origin
   git -C "$Repo" remote get-url --push origin
   ```

3. Выполнить `base_cli.py verify` и тесты до публикации.
4. Публиковать только проверенный main. Автоматическая публикация разрешена
   только hub SessionEnd.

## Consumer

1. Не создавать `.developer-marker` в build-репозитории.
2. После pull проверить:

   ```powershell
   git -C "$Repo" remote get-url --push origin
   # ожидается: NO_PUSH_CONSUMER
   ```

3. Выполнить `/sync-base` или updater.
4. При первом merge shared settings прежние принудительные `xhigh`, plugins,
   marketplace и autoMode удаляются один раз. Личные значения можно задать
   после появления `shared-settings-v2-migrated.flag`.

Локальные коммиты consumer считаются drift. Их нельзя автоматически отправлять
или удалять; нужен отдельный разбор и резервная копия.

## Вывод старого feedback-канала

1. Архивировать feedback-репозиторий read-only.
2. Отозвать его PAT/write-token.
3. Удалить локальный credential-конфиг после подтверждения отзыва.
4. Не переносить старые inbox/staging в новый пакет.

Скрипты collector/pull/token-setup удалены из активной базы. Историческая
инструкция в `memory/feedback_workflow.md` помечена как decommissioned.

## Legacy direct clone

Прямой clone всего build-репозитория в `~/.claude` остаётся несовместимым с
целевым token budget: клиент может автоматически увидеть полный каталог
`agents/` и `skills/`. Целевой Foundation installer должен ставить результат
`base_cli.py render`, а исходный каталог держать вне native discovery paths.

Пока миграция инсталлером не пройдена, нельзя утверждать, что существующий
consumer уже получил полное снижение стартового контекста.

## Rollback

- Git-файлы восстанавливаются из предыдущего commit/пакета.
- `settings.json.bak` содержит состояние до последнего merge.
- Удалённый managed Codex-agent получает `.bak-codex-sync`.
- Возврат consumer write-access требует явного перевода устройства в hub; один
  лишь ручной `git remote set-url --push` не является сменой роли.
