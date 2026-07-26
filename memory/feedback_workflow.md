# Архив: Feedback-канал consumer → hub

> **Выведен из эксплуатации 2026-07-26.** Файл сохранён только как история
> решений. Скрипты, credential-конфиг и SessionEnd upload удалены. Текущий поток
> базы односторонний: hub → consumer; не выполнять инструкции ниже.

Загружать по триггерам: «feedback», «отправить урок в базу», «consumer-ПК», «не пушить
в main», когда Claude на consumer-машине получил урок/правку/нашёл косяк базы.

## Зачем

Чтобы сотрудники (8 машин кроме хаба) могли слать уроки/правки в базу, **НЕ
коммитя в главный claude-base** напрямую (иначе main засоряется непроверенным).

## Два репо

- **claude-base** — главная база. Пушит **только хаб** (dev-ПК с `.developer-marker`).
- **claude-base-feedback** — канал обратной связи. Сюда пушат **consumer**-машины.

## Поток (consumer, без .developer-marker)

1. **Claude в сессии сам пишет** `~/.claude/feedback-pending/<тема>.md` (обезличенно!),
   когда: пользователь скорректировал подход; найден урок/ловушка; косяк скилла/агента;
   дыра в инструментах. Формат: что случилось, Why, How to apply.
2. На SessionEnd `auto-push.ps1` (в consumer-mode) зовёт `feedback-collector.ps1`:
   переносит pending → `feedback-staging/<дата>-<host>-<имя>.md` → пушит в ветку
   `feedback/<hostname>` репо `claude-base-feedback` (если есть `.feedback-config.json`).
3. **Consumer НИКОГДА не пушит в main claude-base.**

## Поток (dev-хаб, есть .developer-marker)

1. `powershell -File ~/.claude/scripts/pull-feedback.ps1` — собирает все ветки
   `feedback/*` в `~/.claude/feedback-inbox/all/<branch>/`.
2. Daniil читает, **курирует** хорошие уроки в main (agents/skills/memory), пушит main.
3. Запускать pull-feedback в начале сессии (иначе consumer-reports не видны —
   см. `projects/.../memory/feedback_pull_feedback_routine.md`).

## Конфиг
`~/.claude/.feedback-config.json`: `github_repo: <логин>/claude-base-feedback`,
PAT зашифрован DPAPI (расшифровать может только тот же user+machine — см.
`projects/.../memory/feedback_dpapi_pat_storage.md`). Установка токена —
`scripts/Set-FeedbackToken.ps1`.

## Правило (главное)
**dev-хаб → push main. Consumer → только feedback-канал, НЕ main.** Определяется
наличием `~/.claude/.developer-marker`.
