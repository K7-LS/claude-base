# claude-base

Общая база Claude Code: глобальные правила (`CLAUDE.md`), 15 доменных и ревьюер-агентов, 16+ методологических скиллов, эмпирическая память, отчёты сессий, harvest внешних инструментов, именованные цепочки (chains).

**Этот репо клонируется в `~/.claude/` каждого ПК пользователя через [claude-lite-instaler](https://github.com/K7-LS/claude-lite-instaler).** Все ПК синхронизируют изменения через git с **hub-and-spoke** архитектурой (developer = DANIILPC пишет в `main`, consumer-ПК сотрудников читают + шлют feedback в отдельный приватный репо `claude-base-feedback`).

## Что внутри

| Папка / файл | Назначение |
|---|---|
| `CLAUDE.md` | Глобальный manifest (де-водизирован 2026-06-02 → ~10 KB чистого UTF-8): STOP-выжимка, 5 принципов Karpathy, 4 правила skill-first, MCP-роутинг, 9 универсальных правил (вкл. нейтральное оформление docx/xlsx и `FACTS.md`), Feedback (dev/consumer), ритуал отчёта. Детали-справочник вынесены в `memory/*.md` (cascade-load по триггеру). Управляется через `claude-lite-instaler` + USER EXTENSIONS внизу. |
| `agents/` | **15 агентов** Claude Code: 7 доменных (`designer`, `pto-engineer`, `сметчик`, `снабженец`, `id-engineer`, `kp-writer`, `letter-writer`, `expertiza-responder`, `norm-lookup`), общий ревьюер (`auditor`), 4 узких ревьюера (`pdf-reviewer`, `excel-validator`, `word-checker`, `audit-rd-section`), межразделный координатор (`rd-coordinator`). См. `templates/agent_TEMPLATE.md` для новых агентов. |
| `skills/` | **16+ скиллов** методологические: `karpathy-guidelines` (5 принципов), `skill-development` (4 правила skill-first), `domain-grilling` (допрос перед строй-задачей), `facts-layer` (единый источник правды — `FACTS.md` ключ→значение→источник, агенты читают первым), `doc-extract` (единственный вход извлечения из PDF) / `pdf-edit` (редактирование PDF, + вшит ВЕРИФИЦИРОВАННЫЙ метод правки вектор-PDF через Inkscape), `excel-helper`, `word-helper` (+ метод правки существующих docx без слома структуры/underline), `chains-pattern`, `structured-artifacts` (cascade loading), `handoff-to-new-chat`, `image-text-replace`, `cad-reader`, `upd-parser`, `spec-writer`, `stroy-formatting`, `yandex-disk-uploader`. |
| `chains/` | **Именованные цепочки** многошаговых сценариев: `docx-from-template`, `pdf-scan-extract`, `project-doc-pack` (stub). Триггерятся по фразам пользователя, выполняются последовательно с verify-критерием на каждом шаге. |
| `memory/` | Эмпирические наблюдения по реальным задачам — feedback, project, reference, user типы. Кейсы провалов и успехов, обезличенные. Также секции CLAUDE.md вынесенные сюда для экономии overhead (`auto_sync.md`, `role_detection.md`, `reference_mcp.md`, `reference_agents.md` и др). |
| `session-reports/` | Per-session reports: каждая закончившаяся сессия складывает сюда `<дата>_<тема>/` с `report.md`, `harvested/`, `artifacts/`. **Имя `session-reports/`, не `sessions/`** — у Claude Code есть своя `~/.claude/sessions/` для transient JSON state. |
| `harvested/` | Каталог внешних инструментов (notes-only). Структурирован по категориям: `pdf/`, `dwg/`, `diagrams/`. Каждая запись — независимая оценка репо/библиотеки с лицензией, активностью, verdict adopted/rejected. |
| `formatting-templates/` | 4 шаблона ГОСТ-стилей DOCX/PDF: `gost-report`, `gost-report-with-border`, `vkr-style`, `plain-clean`. Применяются через скилл `stroy-formatting`. |
| `commands/` | Slash-команды (`/format`, `/harvest`, и др.). |
| `scripts/` | Hooks инфраструктура: `auto-pull.ps1` (SessionStart), `auto-push.ps1` (SessionEnd), `feedback-collector.ps1` (consumer-mode SessionEnd), `merge-shared-settings.ps1`. |
| `anti-patterns.md` | Каталог типичных ошибок и как их избежать. Категории: делегация, скиллы, документы, безопасность, контекст, memory. |
| `CHANGELOG.md` | Журнал обновлений базы — показывается пользователю в первой реплике сессии когда есть свежие изменения. |
| `settings.shared.json` | Shared конфигурация Claude Code hooks. Personal `settings.json` (gitignored) генерируется через `merge-shared-settings.ps1`. |

## Архитектура hub-and-spoke

База синхронизируется через две роли:

| Роль | Маркер | SessionStart | SessionEnd |
|---|---|---|---|
| **Developer** (Daniil, DANIILPC) | Файл `~/.claude/.developer-marker` существует | auto-pull --rebase | auto-push в `claude-base/main` |
| **Consumer** (сотрудники) | Маркера нет | auto-pull --rebase (read-only) | `feedback-collector.ps1` → push в `claude-base-feedback` ветку `feedback/<host>-<user>` через GitHub API + PAT |

**Что попадает в feedback-репо:**
- Файлы из `feedback-pending/*.md` (Claude пишет на ходу при суждениях/ошибках/находках).
- **Untracked `session-reports/*/report.md`** — auto-harvest для сотрудников (фикс 2026-05-26). Hub-and-spoke сохраняется, отчёты сотрудников не теряются.

**Никогда не коммитится** (whitelist подход в `.gitignore`): `.credentials.json`, `history.jsonl`, `plugins/`, `projects/`, `cache/`, `downloads/`, `backups/`, `file-history/`, `_sandbox/`, `.developer-marker`, `.feedback-config.json`.

Лог: `~/.claude/auto-sync.log`. При конфликте rebase — скрипт абортит, ничего не теряет.

## Архитектура агентов и скиллов

Агентская: **main → доменный агент → ревьюер**. Лимит глубины вызовов 2 уровня.

- **Доменные агенты** — узкоспециализированные эксперты по строительной фирме (проектирование инженерных систем, ПТО, снабжение, сметы, исполнительная документация, ответ на экспертизу, КП, деловые письма, поиск по нормативам).
- **Ревьюеры** — независимые, **read-only**, без права записи в файлы. Получают только ТЗ + артефакт, не ход рассуждений автора. Failure-mode строгий: общие фразы «всё ок» = провален.
- **Скиллы** — методология подключаемая по триггерам в SKILL.md frontmatter. Главный — `karpathy-guidelines` (5 принципов поведения).
- **Chains** — формализованные многошаговые pipeline'ы. Главное правило — verify-критерий на каждом шаге.

Подробности — в `CLAUDE.md` и `memory/reference_agents.md` + `memory/reference_mcp.md`.

## Установка

Через [claude-lite-instaler](https://github.com/K7-LS/claude-lite-instaler):

```powershell
git clone https://github.com/K7-LS/claude-lite-instaler
cd claude-lite-instaler
.\Install.ps1
```

Установщик клонирует `claude-base` в `~/.claude/`, настраивает MCP-серверы (9 эталонных: `markitdown`, `document-loader`, `word`, `excel`, `pdf-mcp`, `sequential-thinking`, `fetch`, `time`, `adeu`), прокси-bypass для github.com, hooks, VS Code/Claude Desktop интеграцию.

Обновление на уже установленном ПК — двойной клик `~/.claude/scripts/Update-ClaudeBase.bat`.

## Дисциплина расширения

- **Новый агент** создаётся **только** после ≥3 успешных применений main-агента в этом домене без него.
- **Новых правил наперёд не пишем.** Эмпирические наблюдения → `memory/`, не в инструкции агентов.
- **Внешние инструменты** — через harvest-workflow (см. `CLAUDE.md`): заметки да, копирование кода без явного согласия пользователя — нет.
- **Шаблон агента** `templates/agent_TEMPLATE.md` v1.0 (2026-05-25, адаптация из gsd-redux). Новые агенты по нему. Старые 5 (auditor, designer, excel-validator, pdf-reviewer, word-checker) pre-date шаблон — не выровнены, см. backlog.

## Безопасность

`.gitignore` использует **whitelist-подход** — игнорируется всё, кроме явно разрешённых директорий. Защищает от попадания credentials и истории чатов.

**Никогда** в git:
- `.credentials.json`, `.developer-marker`, `.feedback-config.json` (PAT для feedback-репо)
- `history.jsonl`, `projects/`, `cache/`, `downloads/`, `plugins/`, `backups/`, `file-history/`
- `_sandbox/`, `.feedback-analysis-cache/` (локальные временные данные)

**GitHub доступ:** через bypass корп-прокси (см. `CLAUDE.md` секцию «GitHub bypass proxy»). `git config --global http.https://github.com/.proxy ""` — one-time на каждом ПК.

## История

Старая база v1 (`claude-stroy-base`) с архитектурой «скиллы + lazy-load + триггерные карты в локальном vault» заархивирована:
- Тег `archive/v1-legacy` в репо `claude-stroy-base`.
- Папка на ноутбуке владельца: `Desktop\Обучение и развитие Claude под наши задачи\` — **не использовать** как источник правил (см. CLAUDE.md секцию «Архив старой базы v1»).

Причина перехода: эмпирически доказано что глобальная база в `~/.claude/` с агентами + ревьюерами + hub-and-spoke синхронизацией работает лучше, чем локальный vault с триггерными картами.
