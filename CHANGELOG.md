# CHANGELOG claude-base

Daniil ведёт версии. При каждом значимом обновлении методики — добавить
запись в начало (newest first). Сотрудники видят diff в первой реплике
Claude при новой сессии (через правило в CLAUDE.md).

Формат: дата + список изменений (semver не используется — сразу человеко-читаемые
описания: что добавлено / починено / убрано).

---

## 2026-07-26 — LLM-base v2: компактный контекст, OpenCode и one-way sync

### Изменено

- Общая база стала build-репозиторием с vendor-neutral core и отдельными
  нативными target `claude`, `codex`, `opencode`.
- Kimi больше не target; модель выбирается пользователем через провайдера
  OpenCode без автоматического fallback.
- Стартовый budget каждого target ограничен 3000 оценочных токенов; фактический
  рендер занимает 1901–1976.
- Простой запрос не запускает tools, agents или reviewers.
- Shared Claude settings больше не навязывают xhigh, model, plugins,
  marketplace, prompt/tool telemetry и fan-out.
- Consumer sync стал строго односторонним: push, feedback и session upload
  отключены; старый обратный transport удалён.
- Добавлены безопасный JSONL token audit и отчёт по account-risk без публикации
  prompt/секретов.
- Foundation installer переведён на schema v2 и target-bound пакеты трёх
  клиентов с раздельным state/rollback и consumer-by-default.

### Release gate

Synthetic fake-home tests не равны rollout. До immutable rendered source,
frozen evidence, независимого аудита и отдельно разрешённого canary:
`BLOCKED_APPROVED_FOUNDATION_SOURCE` / `FULL_RELEASE_NOT_PASS`.

## 2026-07-07 — Auto-push ожил (UTF-8 stdin), хуки project-memory включены, пакет Блоков 2/4 дошёл до всех

### Починено
- **auto-push молча НЕ пушил с 02.07**: гейт эфемерных сессий читал stdin хука в
  OEM-кодировке, кириллица в пути транскрипта («C:\Users\<Имя>\…») ломалась,
  `Test-Path` не находил файл → каждый настоящий SessionEnd считался эфемерным.
  Фикс `3d3091c`: UTF-8 InputEncoding + срез BOM в auto-push И auto-pull;
  отсутствующий транскрипт теперь fail-open (пуш идёт). Детали и правило для
  новых хуков — `memory/2026-05-09_hooks-debugging.md`, Урок 17. Самопроверка:
  на настоящем конце сессии в `auto-sync.log` появляется строка
  `real SessionEnd (lines=N, duration_sec=…)`.

### Доехало до origin вместе с фиксом (копилось на хабе 06–07.07)
- **toolgate v2.5**: сессионный гейт по РЕАЛЬНОМУ заполнению контекста (~70% окна 1M)
  вместо счётчика 75 вызовов; байт-прокси — только fallback.
- **project-memory: хуки журнала проекта ВКЛЮЧЕНЫ команде** (settings.shared.json;
  активируются со второго старта Claude на вашем ПК). Карта хуков в CLAUDE.md
  дополнена (SessionStart + Stop).
- **Гигиена Блока 4**: `skills.md` теперь ГЕНЕРИРУЕТСЯ (`scripts/build_skills_index.py`,
  руками не править); шаблон агента в `templates/agent_TEMPLATE.md`; фиксы
  aggregate/pull-feedback (UTF-8/smoke-фильтр); mineru_extract с resume.

### Разбор feedback-inbox (28 ваших отчётов) — конвейер работает
15+ уроков команды уже были мигрированы ранее (ловушки excel-helper пп.9/10/15/16,
anti-patterns A1.5/A3.5, doc-extract CID-рендер, chains, reference_pyrevit и др.);
~10 кандидатов ждут решений владельца. Report'ы с явными «Why/How to apply»
доходят быстрее всего — пишите их.

### Что делать на своём ПК
Ничего: auto-pull заберёт всё при старте новой сессии. `/sync-base` — только если
Claude первой строкой напоминает про extras-флаг.



### Диагноз (аудит из удалённой сессии)
Системная причина трёх хронических симптомов: правила работали только там, где в
always-loaded CLAUDE.md стоял жёсткий гейт (norm-lookup, ревьюер); всё в cascade-памяти
и телах агентов фактически невидимо в момент решения. Frontmatter'ы 16 агентов валидны,
description хорошие — «чинили не тот слой».

### Добавлено / починено
- **CLAUDE.md: роутинг-гейт** — перед доменной работой обязательная видимая строка
  `Роутинг: <домен> → агент <имя> / инлайн — <причина>` (тот же паттерн, что у ревьюера).
- **CLAUDE.md: лестница веб-доступа** (always-loaded): exa → fetch → playwright → WebFetch
  (последняя ступень, 80-90% fail). Провал ступени = перейти дальше, а не «в интернете нет».
- **CLAUDE.md: две ловушки чтения чисел** — xlsx «None ≠ пусто» (формулы без кэша) и
  docx merged-ячейки (счёт N раз). Боевые правила + рецепты: `excel-helper`, `word-helper`;
  независимый пересчёт денег вшит в `excel-validator` и `word-checker` (CRITICAL при расхождении).
- **/sync-base — единая команда**: pull + verify + установка по манифесту. Манифест получил
  `tier: core|optional`, `needs_admin`, `needs_key`; exa добавлен (core). Optional-отказ
  пишется в `.local-state/declined.json`, но в инвентаре показывается всегда.
- **Тихое уведомление об install-долге**: auto-pull при extras-diff ставит
  `.local-state/extras-pending.flag` → STOP-процедура даёт одну строку «запусти /sync-base».
- **Личный слой**: `CLAUDE.user.md` (@import, gitignored) вместо USER EXTENSIONS;
  личные скиллы — префикс `local-`; правило приоритета базы над личным + предложение
  feedback при противоречии.
- **Граф базы — версионируемый навигатор**: .gitignore-исключение для корневого
  `graphify-out/`; правило «вопросы об устройстве базы → graphify query»; правило хаба —
  актуализировать граф при правках базы. Поведенческие правила в граф НЕ выносятся.
- **БАГ-ФИКС: tools-allowlist агентов.** У 7 writer-агентов (сметчик, снабженец,
  pto-engineer, id-engineer, kp-writer, letter-writer, expertiza-responder) тела приказывали
  «создавай через `mcp__excel__*`/`mcp__word__*`», но в `tools:` НЕ БЫЛО ни одного MCP-инструмента —
  выполнить собственную инструкцию они физически не могли. Добавлены поимённые наборы
  (write-наборы writer'ам, read-наборы ревьюерам audit-rd-section/rd-coordinator, exa — сметчику
  и снабженцу). `search_and_replace` writer'ам СОЗНАТЕЛЬНО не выдан (анти-паттерн A3.8 —
  задвоение в таблицах — теперь заблокирован allowlist'ом, а не просьбой).
- **blocks/ — доменные блоки с активацией по роли.** Крупные комплекты (семья агентов +
  каскады + скиллы), нужные не всем: живут в общем репо, активируются профилем через
  /sync-base (копии агентов gitignored), у неактивных стоят 0 токенов кроме роутинг-строки.
  Первый блок — `blocks/pto/` (experimental, глава семьи pto-engineer). UX: триггер темы →
  main предлагает выбор свободной формой (каскад/Workflow/индивидуально) + рекомендация,
  вопрос задаёт оркестратор ДО спавна. См. `blocks/README.md`.
- **Телеметрия инструментов** (обкатка на dev-ПК до раскатки): `scripts/log-tool-usage.ps1`
  (PostToolUse hook, JSONL per-PC) + `scripts/aggregate-tool-usage.ps1` (топы вызовов,
  список молчащих агентов/скиллов). В shared hooks НЕ вшито — сначала практика на хабе.
- **skill-development: правила переиспользования** — query-before-build (graphify query до
  создания нового инструмента), «один дом — остальные ссылаются» (копия правила в теле
  агента не обновится никогда), «гравитация блоков» (нужно второму блоку → в общий слой).
- Одноразовый чек-лист для dev-ноутбука: `docs/2026-06-09-laptop-after-merge.md`.

## 2026-06-02 — PRO-контекст, методы Word/PDF, facts-layer, feedback, установщик

### Починено
- **`CLAUDE.md` — mojibake-кодировка** (хранился в double-encoded UTF8→CP1251).
  Переписан в чистый UTF-8 + де-водизирован: 64 KB→10 KB, 489→111 строк. На PRO-окне
  (200K) это **−15% окна** (раньше старый CLAUDE.md ел ~17% = ~34k токенов). **Лечение
  всем: `/sync-base`.** Если контекста по-прежнему не хватает — обнови Claude Code
  (нужна версия с tool-search/deferred MCP) и проверь `$env:ENABLE_TOOL_SEARCH` ≠ false.
- **Feedback-триггер** восстановлен в `CLAUDE.md` (секция Feedback) — был потерян,
  поэтому consumer-Claude не писал `feedback-pending` и все коммитили в main. Правило:
  **dev→main, consumer→feedback-канал** (по `.developer-marker`).
- **Ритуал отчёта сессии** возвращён в `CLAUDE.md` (де-водизация его ослабила).

### Добавлено
- **skill `facts-layer`** — единый источник правды по проекту `FACTS.md`
  (ключ→значение→источник). Доменные агенты читают первым; факт правится в одном
  месте → нет рассинхрона между спецификацией/КП/сметой. + `CLAUDE.md` правило #9.
- **`pdf-helper`** — вшит **ВЕРИФИЦИРОВАННЫЙ** метод правки вектор-PDF (Inkscape:
  Внутренний импорт → выделить → Delete/move → export, проверка рендером). Inkscape
  ставится **отдельно** руками (`winget install Inkscape.Inkscape`).
- **`word-helper`** — метод правки существующих docx без слома структуры/underline
  (дамп структуры → inline-шапка → не трогать табы → verify-гейт PDF-рендером).
- **`CLAUDE.md` правило #8** — оформление деловых docx/xlsx **нейтральное**, без
  декоративного синего «Claude-стиля». Детали — `word-helper`/`excel-helper`.
- **`memory/`** — `feedback_workflow.md`, `reference_docx_editing_failures.md`,
  `proxy_github.md`, `harvest_workflow.md`, `auto_memory_policy.md`, `named_chains.md`,
  `context_discipline.md`, `archive_v1.md` (вынос из CLAUDE.md).

### Установщик (claude-lite-instaler)
- **Feedback** из «опционально в тексте» → **заметный prompted-шаг** в конце установки.
- Визуальный апгрейд: banner, стилизованные секции, `✓` финал, UTF-8 вывод.

## 2026-05-26 — Knowledge library (база ГОСТ/СП/СНиП/постановлений)

### Добавлено

- **`library/`** — каркас локальной библиотеки нормативных документов:
  INDEX.md + 8 категорий (spds/ov/vk/eo/ss/ppr/prikazy/shablony) + README.
  Закрывает класс ошибок 2026-05-25 (выдумывание норм по памяти агентами:
  сметчик ПДВ/НДС, audit-rd-section СП 76 vs СП 256, маркировка П/В).
- **`scripts/Set-LibraryRoot.ps1`** — интерактивный per-PC setup helper
  для регистрации пути до shared папки на Я.Диске.
- **`agents/norm-lookup.md`** — расширен под библиотеку: 8 новых
  `mcp__pdf-mcp__*` и `mcp__word__*` read-only tools, алгоритм поиска
  по INDEX, **10 структурированных failure modes**: `NO_CONFIG`,
  `NO_INVITE`, `SYNC_IN_PROGRESS`, `NOT_IN_INDEX`, `NOT_DOWNLOADED`,
  `NO_TEXT_LAYER`, `WEBFETCH_BLOCKED`, `CANCELLED`, `SUPERSEDED`,
  `NOT_FOUND`. **Запрет выдумывания** усилен.
- **`CLAUDE.md` правило #7** — «нормы только через `norm-lookup`».
- **`.gitignore`** — whitelist `library/` + hard-block
  `.library-config.json` (per-PC, никогда в git).
- **Spec:** `docs/superpowers/specs/2026-05-26-knowledge-library-design.md`.
- **Plan:** `docs/superpowers/plans/2026-05-26-knowledge-library.md`.

### Сотруднику сделать (one-time setup)

После следующего auto-pull тебе нужно сделать **3 шага** руками:

**1. Принять invite от Daniil** на папку `Claude_Library` в веб-интерфейсе
Яндекс.Диска. Раздел «Доступы» → принять. На твоём Я.Диске появится
shared папка (возможно с префиксом «От Даниила» или похожим именем).

**2. Дождаться окончания первичного sync** Яндекс.Диск-клиента на твоём
ПК (10-30 минут в зависимости от размера библиотеки на момент инвайта).
В трее Я.Диска должно перестать крутиться «Синхронизация...».

**3. Запустить helper:**

```powershell
& "$env:USERPROFILE\.claude\scripts\Set-LibraryRoot.ps1"
```

Скрипт спросит полный путь до Claude_Library на твоём ПК. Default —
`C:\Users\<имя>\YandexDisk\Claude_Library`, но если shared папка имеет
другое имя — введи её полный путь. Скрипт проверит существование, посчитает
PDF, запишет `~/.claude/.library-config.json`.

**4. (Опционально, но рекомендую) Restart Claude Code** — чтобы агент
`norm-lookup` подхватил новые tools (`mcp__pdf-mcp__*` и `mcp__word__*`).
Без restart агент работает по старому whitelist'у.

### Что изменится после setup

Любой нормативный запрос (например «что говорит ГОСТ 21.101 про штамп»?)
будет автоматически идти через `norm-lookup`. Агент:

1. Прочитает локальный INDEX.md.
2. Найдёт нужную норму.
3. Прочитает PDF из shared папки через MCP.
4. Вернёт **дословную цитату** + номер пункта + редакцию + источник.

Никаких выдумок «по памяти» — только проверяемые цитаты.

### Backward compat

Пока библиотека не наполнена (Daniel добавляет нормы постепенно) —
`norm-lookup` будет отвечать `NOT_IN_INDEX` и пробовать WebFetch на
cntd.ru. По мере наполнения — всё больше запросов будет обслуживаться
локально из библиотеки.

---

## 2026-05-26 — Безопасность + надёжность инфры

### Починено

- **Hub-and-spoke дыра** (`scripts/feedback-collector.ps1`):
  consumer-ПК теперь auto-harvest'ит untracked `session-reports/*/report.md`
  и шлёт их через GitHub API в `claude-base-feedback`. Раньше отчёты
  сотрудников копились локально и терялись (см. `session-reports/2026-05-26_auto-push-fix-consumer-mode/`).

### Добавлено

- **`scripts/Set-FeedbackToken.ps1`** — шифрование GitHub PAT в `.feedback-config.json`
  через Windows DPAPI CurrentUser scope. PAT больше не лежит в plaintext.
- **`skills/structured-artifacts/`** — методология выноса контекста крупных
  задач (3+ фазы, multi-agent) в md-файлы ROADMAP/STATE/PLAN/REVIEW/DECISIONS.
  Адаптация Концепта 2 из gsd-redux.
- **`harvested/pdf/pikepdf.md`** — заметка про pikepdf (низкоуровневое
  редактирование PDF content stream, физический вырез старого штампа
  через clip-path inject).
- **anti-patterns.md A3.5** — PyMuPDF apply_redactions/show_pdf_page
  не удаляет Form XObjects (закрывает класс ловушек «двойной слой»).
- **anti-patterns.md A4.3a** — PAT в plaintext конфигах → DPAPI.
- **karpathy-guidelines: harvest-first правило** — 2 итерации без
  рабочего результата → `/harvest` ПРЕЖДЕ обходных подходов.

### Сотруднику сделать (на каждом consumer-ПК)

После следующего `auto-pull` (запустится при следующей сессии Claude
Code) — один раз запустить шифрование PAT:

```powershell
& "$env:USERPROFILE\.claude\scripts\Set-FeedbackToken.ps1"
```

Скрипт спросит PAT (текущий, тот же что в `~/.claude/.feedback-config.json`
поле `token`). Зашифрует через DPAPI, обнулит plain token. После этого
плэйнтекст PAT нигде не хранится. Старый plain token продолжит работать
до миграции (WARN в auto-sync.log), так что fail-safe есть.

При переустановке Windows / переносе профиля — запустить скрипт заново
(DPAPI ключ привязан к user+machine).

---

## 2026-05-22 — Updater 2.0 (one-command setup)

### Добавлено

- **`scripts/Update-ClaudeBase.ps1`** — single-command setup для любого ПК.
  Делает за один запуск:
    1. Detect role (developer vs consumer)
    2. git pull origin main (с retry + bypass-proxy)
    3. merge-shared-settings
    4. verify-claude-base (22-23 проверки)
    5. (consumer only) prompt для PAT интерактивно + создание .feedback-config.json
    6. (consumer only) smoke-test push в claude-base-feedback
    7. Финальный summary PASS/FAIL по каждому шагу
- **`scripts/Update-ClaudeBase.bat`** — double-click wrapper. Сотрудник
  открывает проводник `~/.claude/scripts/`, делает двойной клик на
  Update-ClaudeBase.bat — всё автоматически.

### Починено

- verify-claude-base.ps1 устарел после Phase 1 — проверял `settings.json`
  в whitelist (мы его вынесли в gitignored). Заменено на проверку
  `settings.shared.json` + добавлена inverse check «settings.json **не**
  в whitelist».

### Как использовать (для сотрудника)

1. Открыть проводник, перейти в `C:\Users\<user>\.claude\scripts\`
2. Двойной клик на **Update-ClaudeBase.bat**
3. Если первая установка — скрипт интерактивно спросит PAT (получить
   от Daniil'а по secure channel).
4. Финал: либо `✅ Готово` либо `❌ Есть FAIL` с конкретной диагностикой.

---

## 2026-05-21 — Phase 2-follow-up: remote feedback

### Добавлено

- **`scripts/feedback-collector.ps1`** расширен GitHub API push:
  - Авто-создание branch `feedback/<hostname>-<userprefix>` от main
  - PUT `/repos/.../contents/feedback/<filename>` с PAT auth
  - После push → файл переезжает в `feedback-staging/pushed/`
  - Idempotent через GitHub SHA matching
- **`scripts/pull-feedback.ps1`** — для Daniil'а. Clone/fetch claude-base-feedback,
  list всех `feedback/*` веток, copy файлов в `~/.claude/feedback-inbox/all/`.
  Mark NEW vs already-seen.
- **Документ** `session-reports/2026-05-21_sync-redesign/phase2-followup-feedback-setup.md`:
  step-by-step что Daniil делает в GitHub UI (создать private repo,
  add collaborators, выдать PAT, распределить, убрать collaborators из main).

### Что осталось руками для Daniil'а

1. Создать private repo `claude-base-feedback` через GitHub UI
2. Добавить collaborators с write
3. Выдать PAT каждому сотруднику
4. На каждом consumer ПК создать `.feedback-config.json` с repo+token
5. Убрать collaborators из main `claude-base`

См. полный план в `session-reports/2026-05-21_sync-redesign/phase2-followup-feedback-setup.md`.

---

## 2026-05-21 — Phase 1+2 sync-redesign

**Архитектурный сдвиг от peer-to-peer git к hub-and-spoke.**

### Что изменилось

- **settings.json вынесен из git** (gitignored). Claude Code UI на каждом
  ПК пишет туда личные настройки — больше никаких merge conflict'ов
  между ПК.
- **settings.shared.json** — новый файл в git. Содержит **намеренные
  правила команды**: language=russian, effortLevel=xhigh, autoMode.allow,
  enabledPlugins, hooks.
- **scripts/merge-shared-settings.ps1** — раз вливает shared → local
  при auto-pull. Не перезаписывает UI-driven theme/viewMode.
- **Role detection** через `~/.claude/.developer-marker` (gitignored).
  DANIILPC = developer (push в main). Остальные = consumer
  (feedback-collect вместо push).
- **scripts/feedback-collector.ps1** — на consumer ПК собирает feedback
  файлы локально в `feedback-staging/`. Если есть `.feedback-config.json`
  с GitHub репо — push через API (TODO Phase 2-follow-up).
- **CHANGELOG.md** — этот файл. Сотрудники видят diff в первой реплике
  Claude.

### Что добавлено сегодня (Daniil session 2026-05-21)

- skills/handoff-to-new-chat (proactive handoff при перегрузе контекста)
- scripts/verify-claude-base.ps1 (smoke-test 22 пункта)
- scripts/auto-pull.ps1, auto-push.ps1 — retry logic + WARN + DONE + role detection
- scripts/setup-extras.ps1 — Step 0 (auto-apply git config bypass-proxy для GitHub)
- skills/image-text-replace v3.1 — calibration-guard + unify_font_size_for_batch + refine_bg_with_diffusion preference (LESSONS-LEARNED §6, §7)
- evals/ — 21 pytest regression-тест для image-text-replace
- chains/ — 3 named chain (docx-from-template, pdf-scan-extract, project-doc-pack)
- skills/chains-pattern — методология named chains
- anti-patterns.md — Категория 6 (дисциплина контекста)
- CLAUDE.md — разделы: дисциплина контекста, GitHub bypass-proxy, chains, role detection

---

## 2026-05-20 — Импорт из <организация> audit

- Audit чужой базы <организация> (агенты) — отчёт `~/Desktop/<организация>_audit_report.docx`
- GH-600 study guide на русском — `~/Desktop/GH-600_study_guide_ru.docx`
- chains/ создан как first-class сущность оркестратора
- karpathy-guidelines §4 расширен — verify-criteria для делегаций
- image-text-replace v3.0 — production-ready после 16 итераций (КП <организация> АХП case)
- formatting-templates починены (portrait A4, ГОСТ-поля)

---

## Как пополнять CHANGELOG

Daniil после каждого значимого коммита в main:

1. Открыть `~/.claude/CHANGELOG.md`
2. В **начало** добавить новую секцию формата:

   ```markdown
   ## YYYY-MM-DD — Краткий заголовок

   - что добавлено
   - что починено
   - что убрано (явно сказать deprecation)
   ```

3. Commit + push с CHANGELOG.md (он в auto-push whitelist).

Сотрудники при следующей сессии Claude увидят в первой реплике:
> ✓ База обновлена YYYY-MM-DD: <заголовок> (3 изменения)

См. правило «CHANGELOG notification в первой реплике» в CLAUDE.md.
