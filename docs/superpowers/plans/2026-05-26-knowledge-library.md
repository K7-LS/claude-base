# Knowledge Library Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Внедрить локальную lazy-loaded библиотеку нормативных документов (ГОСТ/СП/СНиП/ПУЭ/постановлений) с расшаренной папкой на Я.Диске владельца + тонким индексом в git claude-base + расширенным `norm-lookup` агентом, чтобы все 9 ПК команды имели доступ к дословным цитатам норм без раздутия контекста и без выдумывания.

**Architecture:** Owner (DANIILPC) хранит PDF/DOCX норм в `<YandexDisk>/Claude_Library/`, расшаривает папку на чтение 8 сотрудникам через веб Я.Диска. Тонкий индекс (INDEX.md + categories/) + helper скрипт + правки агента/CLAUDE.md лежат в git claude-base — раздаются auto-pull'ом. Per-PC `.library-config.json` хранит полный путь до Я.Диск папки (gitignored, разный на каждом ПК). `norm-lookup` агент при запросе нормы читает INDEX → находит файл → читает PDF через `mcp__pdf-mcp__pdf_search` → возвращает структурированный ответ (документ + пункт + цитата + достоверность). Failure modes структурированные: `NO_CONFIG`, `NO_INVITE`, `SYNC_IN_PROGRESS`, `NOT_IN_INDEX`, `NOT_DOWNLOADED`, `WEBFETCH_BLOCKED`, `CANCELLED`, `SUPERSEDED`, `NOT_FOUND` — никакого выдумывания.

**Tech Stack:** Markdown (с YAML frontmatter), PowerShell 5.1, Git, mcp__pdf-mcp, mcp__word.

---

### Task 1: Скелет library/ — README + INDEX + 8 пустых categories

**Files:**
- Create: `~/.claude/library/README.md`
- Create: `~/.claude/library/INDEX.md`
- Create: `~/.claude/library/categories/spds.md`
- Create: `~/.claude/library/categories/ov.md`
- Create: `~/.claude/library/categories/vk.md`
- Create: `~/.claude/library/categories/eo.md`
- Create: `~/.claude/library/categories/ss.md`
- Create: `~/.claude/library/categories/ppr.md`
- Create: `~/.claude/library/categories/prikazy.md`
- Create: `~/.claude/library/categories/shablony.md`

- [ ] **Step 1: Создать `library/README.md`** — документация что это, кому, как пополнять

```markdown
---
created: 2026-05-26
owner: Daniil Eliseev
status: active
---

# Library — локальная база нормативных документов

Lazy-loaded библиотека ГОСТ/СП/СНиП/ПУЭ/постановлений/шаблонов для
агентов Claude (главным образом `norm-lookup`). PDF файлы лежат на
1ТБ Я.Диске владельца (Daniil), расшарены на чтение всем 9 ПК команды.
Метаданные (этот README, INDEX.md, categories/) лежат в git claude-base
и раздаются через auto-pull.

## Зачем

Закрывает класс ошибок 2026-05-25 — выдумывание норм агентами по
памяти (сметчик ПДВ/НДС, audit-rd-section СП 76 vs СП 256, маркировка
П/В). Любая нормативная ссылка теперь требует **дословной цитаты
из PDF** через `norm-lookup`.

## Структура

- `INDEX.md` — плоская таблица всех документов (ID, категория, файл, год, статус).
- `categories/<имя>.md` — расширенные аннотации по каждому документу категории.
- `extracts/` (пустая на старте) — будут md-конспекты ключевых норм когда понадобится.

## Категории

| Префикс | Тема |
|---------|------|
| spds- | СПДС (ГОСТ 21.xxx) |
| ov- | Отопление, вентиляция, кондиционирование |
| vk- | Водоснабжение, канализация |
| eo- | Электрика, ПУЭ |
| ss- | Слаботочные системы |
| ppr- | Постановления Правительства РФ |
| prikazy- | Приказы Минстроя/Минрегиона |
| shablon- | Шаблоны и примеры оформления |

## Как добавить новый документ (только Daniil)

1. Положить PDF/DOCX в `<YandexDisk>/Claude_Library/<категория>/<имя>.pdf`.
2. Дождаться синхронизации Я.Диска на других ПК (10-30 минут).
3. Добавить строку в `INDEX.md` (см. формат там).
4. Опционально — секция в `categories/<категория>.md` с ключевыми пунктами.
5. `git add` + commit + push.

## Как Claude использует библиотеку

Через агента `norm-lookup`. Алгоритм описан в `agents/norm-lookup.md`.
Главный Claude и доменные агенты НЕ цитируют нормы по памяти —
делегируют `norm-lookup` для получения дословной цитаты.

См. `docs/superpowers/specs/2026-05-26-knowledge-library-design.md` —
полный design документ.
```

- [ ] **Step 2: Создать `library/INDEX.md`** — пустой скелет с заголовком, легендой статусов, форматом таблицы

```markdown
---
status: active
updated: 2026-05-26
---

# Library INDEX

Главный каталог локальной библиотеки нормативных документов.
Читается агентом `norm-lookup` при каждом нормативном запросе.

**Формат:** одна строка на документ. Поля:
- `ID` — уникальный идентификатор (`<категория>-<краткое-имя>`)
- `Категория` — СПДС / ОВ / ВК / ЭО / СС / ППР / Приказы / Шаблоны
- `Документ` — короткий идентификатор (ГОСТ XX.XXX-YYYY, СП XX.YYYY)
- `Полное название` — официальное название документа
- `Файл (rel)` — путь относительно корня `Claude_Library/`
- `Год` — год редакции
- `Статус`:
  - `actual` — действующий
  - `superseded:<id>` — заменён другим (см. указанный ID)
  - `cancelled` — отменён без замены
  - `template` — шаблон оформления (не норматив)

## Каталог

| ID | Категория | Документ | Полное название | Файл (rel) | Год | Статус |
|----|-----------|----------|-----------------|------------|-----|--------|

<!-- Daniil добавляет строки сюда по мере наполнения. -->

## Сводка

- Всего документов: 0
- actual: 0
- superseded: 0
- cancelled: 0
- template: 0

(Обновляется вручную при добавлении.)
```

- [ ] **Step 3: Создать 8 пустых categories/<имя>.md** через цикл PowerShell

Run:
```powershell
$cats = @(
  @{file='spds.md'; title='СПДС'; desc='ГОСТ 21.xxx — оформление проектной и рабочей документации'},
  @{file='ov.md'; title='ОВ — отопление, вентиляция, кондиционирование'; desc='СП 60.13330, СП 7.13130 и связанные'},
  @{file='vk.md'; title='ВК — водоснабжение и канализация'; desc='СП 30.13330, СП 31.13330, СП 32.13330 и связанные'},
  @{file='eo.md'; title='ЭО — электрика'; desc='ПУЭ, СП 256.1325800, СП 76.13330 (отменён, см. СП 256)'},
  @{file='ss.md'; title='СС — слаботочные системы'; desc='СП 134.13330, СП 1.13130, СП 5.13130 (отменён) и связанные'},
  @{file='ppr.md'; title='Постановления Правительства РФ'; desc='ПП 87 (состав ПД), ПП 145 (экспертиза) и др.'},
  @{file='prikazy.md'; title='Приказы Минстроя/Минрегиона'; desc='Текущие приказы регулятора'},
  @{file='shablony.md'; title='Шаблоны и примеры оформления'; desc='Образцы ПЗ, спецификаций, штампов — не нормативы, а готовые шаблоны для копирования'}
)
foreach ($c in $cats) {
  $path = "$env:USERPROFILE\.claude\library\categories\$($c.file)"
  $content = @"
---
category: $($c.title)
status: active
updated: 2026-05-26
---

# Категория: $($c.title)

**О категории:** $($c.desc).

<!--
Формат добавления документа:

## <Документ> — <короткое название>

**Полное название:** <официальное название>
**Статус:** actual / superseded:<id> / cancelled
**Файл:** `<подкатегория>/<имя.pdf>`
**О чём:** 1-2 строки.
**Когда применять:** когда нужен этот документ.
**Ключевые пункты:**
- §X — что регулирует
- §Y — что регулирует
-->
"@
  [System.IO.File]::WriteAllText($path, $content, [System.Text.UTF8Encoding]::new($false))
  Write-Output "Created: $path"
}
```

Expected: 8 строк `Created: ...`, по одной на категорию.

- [ ] **Step 4: Verify файлы созданы**

Run: `ls ~/.claude/library/categories/ && cat ~/.claude/library/README.md | head -5`
Expected: 8 файлов категорий + первые строки README.

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add library/
git commit -m "feat(library): скелет (README + INDEX + 8 categories)"
```

---

### Task 2: .gitignore — добавить .library-config.json

**Files:**
- Modify: `~/.claude/.gitignore`

- [ ] **Step 1: Найти секцию Hard blocks и добавить `.library-config.json`**

Read `~/.claude/.gitignore` чтобы найти секцию для per-PC секретов (там уже есть `.feedback-config.json` или `.developer-marker`).

Добавить строку:
```
.library-config.json
```

- [ ] **Step 2: Verify через `git check-ignore`**

```powershell
cd $env:USERPROFILE\.claude
git check-ignore -v .library-config.json
```
Expected: одна строка с правилом `.gitignore:<N>:.library-config.json`.

- [ ] **Step 3: Commit**

```powershell
git add .gitignore
git commit -m "chore(gitignore): .library-config.json per-PC (PAT не там, путь Я.Диска)"
```

---

### Task 3: Set-LibraryRoot.ps1 — per-PC setup helper

**Files:**
- Create: `~/.claude/scripts/Set-LibraryRoot.ps1`

- [ ] **Step 1: Создать `scripts/Set-LibraryRoot.ps1`**

```powershell
<#
.SYNOPSIS
Per-PC setup helper для knowledge library. Спрашивает у пользователя
полный путь к папке Claude_Library на этом ПК и записывает в
~/.claude/.library-config.json.

.DESCRIPTION
На DANIILPC (owner): создаёт 8 категорийных подпапок если их нет.
На consumer ПК: только регистрирует путь (read-only режим).

Запускается ОДИН РАЗ при первой установке + повторно при переустановке
Windows или смене пути Я.Диска.

Не интерактивный для hook'ов — только manual запуск.
#>

$ErrorActionPreference = 'Stop'

$ClaudeDir = Join-Path $env:USERPROFILE '.claude'
$ConfigFile = Join-Path $ClaudeDir '.library-config.json'
$DeveloperMarker = Join-Path $ClaudeDir '.developer-marker'

Write-Host ""
Write-Host "=== Set-LibraryRoot: настройка knowledge library ===" -ForegroundColor Cyan
Write-Host ""

# 1. Определить роль
$isDeveloper = Test-Path $DeveloperMarker
if ($isDeveloper) {
    Write-Host "Роль: developer (DANIILPC). Подпапки будут созданы если их нет." -ForegroundColor Green
} else {
    Write-Host "Роль: consumer. Read-only режим: подпапки должны быть уже подтянуты через Я.Диск sync." -ForegroundColor Yellow
}

# 2. Спросить путь
$defaultPath = Join-Path $env:USERPROFILE "YandexDisk\Claude_Library"
Write-Host ""
Write-Host "Введи полный путь до папки Claude_Library на этом ПК." -ForegroundColor Cyan
Write-Host "  - На DANIILPC: '$defaultPath' или другой если Я.Диск в другом месте." -ForegroundColor Gray
Write-Host "  - На consumer ПК: путь к shared папке, как её показывает Я.Диск" -ForegroundColor Gray
Write-Host "    (может быть с префиксом 'От Даниила' или похожим)." -ForegroundColor Gray
$inputPath = Read-Host "Путь (Enter для default: $defaultPath)"
if (-not $inputPath) { $inputPath = $defaultPath }

# 3. Проверить существование
if (-not (Test-Path $inputPath)) {
    if ($isDeveloper) {
        Write-Host ""
        Write-Host "Папка не существует. Создаю (developer mode)." -ForegroundColor Yellow
        New-Item -ItemType Directory -Path $inputPath -Force | Out-Null
    } else {
        Write-Host ""
        Write-Host "ERROR: папка '$inputPath' не существует." -ForegroundColor Red
        Write-Host "Шаги для consumer ПК:" -ForegroundColor Yellow
        Write-Host "  1. Открой Я.Диск в браузере → раздел 'Доступы'." -ForegroundColor Yellow
        Write-Host "  2. Прими invite от Daniil на папку Claude_Library." -ForegroundColor Yellow
        Write-Host "  3. Дождись окончания первичного sync Я.Диск-клиента (10-30 минут)." -ForegroundColor Yellow
        Write-Host "  4. Запусти этот скрипт заново." -ForegroundColor Yellow
        exit 1
    }
}

# 4. На developer — создать 8 подпапок
if ($isDeveloper) {
    $subdirs = @('spds', 'ov', 'vk', 'eo', 'ss', 'ppr', 'prikazy', 'shablony')
    foreach ($sub in $subdirs) {
        $subPath = Join-Path $inputPath $sub
        if (-not (Test-Path $subPath)) {
            New-Item -ItemType Directory -Path $subPath -Force | Out-Null
            Write-Host "  + создана подпапка: $sub" -ForegroundColor Green
        }
    }
}

# 5. Smoke check: посчитать PDF в библиотеке
$pdfCount = 0
$subFound = 0
foreach ($sub in @('spds', 'ov', 'vk', 'eo', 'ss', 'ppr', 'prikazy', 'shablony')) {
    $subPath = Join-Path $inputPath $sub
    if (Test-Path $subPath) {
        $subFound++
        $pdfCount += @(Get-ChildItem $subPath -Filter '*.pdf' -ErrorAction SilentlyContinue).Count
    }
}

if ($subFound -eq 0 -and -not $isDeveloper) {
    Write-Host ""
    Write-Host "WARN: ни одной из 8 ожидаемых подпапок не найдено." -ForegroundColor Yellow
    Write-Host "Я.Диск ещё не закончил sync? Подожди и проверь снова через 'ls $inputPath'." -ForegroundColor Yellow
}

# 6. Записать конфиг
$cfg = [PSCustomObject]@{
    library_path = $inputPath
}
$json = $cfg | ConvertTo-Json -Depth 5
[System.IO.File]::WriteAllText($ConfigFile, $json, [System.Text.UTF8Encoding]::new($false))

Write-Host ""
Write-Host "OK. Конфиг записан: $ConfigFile" -ForegroundColor Green
Write-Host "  library_path: $inputPath" -ForegroundColor Green
Write-Host "  Найдено подпапок: $subFound / 8" -ForegroundColor Green
Write-Host "  Найдено PDF: $pdfCount" -ForegroundColor Green
Write-Host ""
Write-Host "Готово. После restart Claude Code агент 'norm-lookup' будет использовать эту библиотеку." -ForegroundColor Cyan
```

- [ ] **Step 2: Smoke test на DANIILPC**

Run:
```powershell
& "$env:USERPROFILE\.claude\scripts\Set-LibraryRoot.ps1"
```

Когда скрипт попросит путь — нажать **Enter** для default `$env:USERPROFILE\YandexDisk\Claude_Library`.

Expected:
- Сообщение «Роль: developer».
- Если папка не существует — создаётся 8 подпапок.
- Сообщение «OK. Конфиг записан».
- Файл `~/.claude/.library-config.json` существует.

- [ ] **Step 3: Verify config**

Run:
```powershell
cat "$env:USERPROFILE\.claude\.library-config.json"
```
Expected:
```json
{
    "library_path":  "C:\\Users\\Даниил\\YandexDisk\\Claude_Library"
}
```

- [ ] **Step 4: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add scripts/Set-LibraryRoot.ps1
git commit -m "feat(scripts): Set-LibraryRoot.ps1 - per-PC setup для knowledge library"
```

---

### Task 4: norm-lookup агент — расширение tools + алгоритм + failure modes

**Files:**
- Modify: `~/.claude/agents/norm-lookup.md`

- [ ] **Step 1: Прочитать текущий norm-lookup.md** для понимания размера и стиля

Run: `cat ~/.claude/agents/norm-lookup.md | head -80`

- [ ] **Step 2: Заменить YAML frontmatter — расширить tools whitelist**

Use Edit tool to replace:
```yaml
tools: Read, Bash, Grep, Glob, WebFetch
```

With:
```yaml
tools: Read, Bash, Grep, Glob, WebFetch, mcp__pdf-mcp__pdf_info, mcp__pdf-mcp__pdf_search, mcp__pdf-mcp__pdf_read_pages, mcp__pdf-mcp__pdf_get_toc, mcp__pdf-mcp__pdf_render_pages, mcp__word__get_document_text, mcp__word__find_text_in_document, mcp__word__get_document_outline
```

- [ ] **Step 3: Добавить секцию «Алгоритм поиска» после секции «When to invoke»**

Use Edit tool to insert before секции «Выход / формат ответа» (или в конец если её нет) следующий блок:

```markdown
## Алгоритм поиска (Phase 2 — knowledge library 2026-05-26)

```
Step 1: Прочитать ~/.claude/.library-config.json → library_path.
        Если файла нет → failure mode NO_CONFIG → WARN + WebFetch fallback.

Step 2: Прочитать ~/.claude/library/INDEX.md (~3-12K токенов).
        Найти подходящие записи по ключевым словам / категории / ID / году.
        Если совпадений несколько — вернуть все пользователю для уточнения.
        Если 0 совпадений → failure mode NOT_IN_INDEX → WebFetch fallback.

Step 3: (опционально) Прочитать categories/<категория>.md для аннотации
        ключевых пунктов — помогает понять куда смотреть в PDF.

Step 4: Собрать абсолютный путь: <library_path>\<file_rel>

Step 5: Проверить существование файла (Test-Path / Glob).
        Если файла нет на диске → failure mode NOT_DOWNLOADED →
        WARN «проверь sync Я.Диска» + WebFetch fallback.

Step 6: mcp__pdf-mcp__pdf_info → проверить text_layer.
        Если text_layer=false → failure mode NO_TEXT_LAYER →
        переключиться на pdf_render_pages + OCR через image-text-replace.
        Пометка достоверности `OCR_low_confidence`.

Step 7: mcp__pdf-mcp__pdf_search "ключевое слово" → 1-3 фрагмента.
        Если нужно — pdf_read_pages для контекста N..N+2.

Step 8: Вернуть структурированный ответ:
        ─ Документ: <полное название + редакция>
        ─ Пункт: <номер раздела/пункта>
        ─ Цитата: «<дословный текст>»
        ─ Источник: <путь к файлу>
        ─ Достоверность: locally_read_PDF | cntd_ru_WebFetch | OCR_low_confidence | NOT_FOUND
```

## Failure modes (структурированные)

| Код | Условие | Поведение |
|-----|---------|-----------|
| `NO_CONFIG` | `.library-config.json` отсутствует | WARN. Fallback на WebFetch. Подсказка: «запусти Set-LibraryRoot.ps1». |
| `NO_INVITE` | `library_path` указан, но папка не существует | Подсказка сотруднику: «прими invite от Daniil, дождись sync, перезапусти Set-LibraryRoot». Fallback на cntd.ru. |
| `SYNC_IN_PROGRESS` | Папка существует, но ни одной подкатегории | Сообщить «Я.Диск синхронизирует». Fallback на cntd.ru. |
| `NOT_IN_INDEX` | INDEX.md не содержит запрошенной нормы | WebFetch cntd.ru попытка → если найдено, пометка `cntd_ru_WebFetch`. |
| `NOT_DOWNLOADED` | В INDEX есть, файла на диске нет | Сообщить «файл не доехал на Я.Диск». Fallback на cntd.ru. |
| `NO_TEXT_LAYER` | PDF — скан | Auto-switch на pdf_render_pages + OCR. Пометка `OCR_low_confidence`. |
| `WEBFETCH_BLOCKED` | cntd.ru заблокирован / 403 / timeout | Честно «не нашёл, прокси/cntd.ru недоступен». Запрос пользователю — добавить норму. **ЗАПРЕТ выдумывания.** |
| `CANCELLED` | Норма со статусом `cancelled` в INDEX | Цитата + явное предупреждение «отменена, для новых проектов не использовать». |
| `SUPERSEDED` | Норма со статусом `superseded:<id>` | Цитата + ссылка на актуальную редакцию. |
| `NOT_FOUND` | Ничего не нашлось ни локально, ни через WebFetch | Честно сказать «не нашёл». **ЗАПРЕТ выдумывания.** Спросить пользователя добавить норму в библиотеку. |

**Главное правило:** при любом failure mode возврат **должен быть явно
помечен** одним из этих кодов. Запрещено возвращать «не нашёл» без кода
или выдумывать цитату. Это противоречит цели агента.
```

- [ ] **Step 4: Verify файл валиден**

Run:
```powershell
$content = Get-Content "$env:USERPROFILE\.claude\agents\norm-lookup.md" -Raw
if ($content -match '(?s)^---\s*\n(.+?)\n---') {
    Write-Output "frontmatter OK"
    $mcpCount = ([regex]::Matches($matches[1], 'mcp__\w[\w-]*__\w+')).Count
    Write-Output "mcp tools count: $mcpCount"
}
Select-String -Path "$env:USERPROFILE\.claude\agents\norm-lookup.md" -Pattern 'NO_CONFIG|NOT_IN_INDEX|NO_INVITE' | Measure-Object | % {"failure modes mentioned: $($_.Count)"}
```

Expected: `frontmatter OK`, `mcp tools count: 8`, `failure modes mentioned: 3` (или больше).

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add agents/norm-lookup.md
git commit -m "feat(agents): norm-lookup расширен для knowledge library (PDF MCP + алгоритм + failure modes)"
```

---

### Task 5: CLAUDE.md — правило #7 «Нормы только через norm-lookup»

**Files:**
- Modify: `~/.claude/CLAUDE.md`

- [ ] **Step 1: Найти секцию «Универсальные правила работы»**

Run:
```powershell
Select-String -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Pattern "Универсальные правила работы" | Select-Object -First 1
```
Expected: одна строка с номером.

- [ ] **Step 2: Найти последнее правило (обычно 6 — «Обезличивание»)**

Run:
```powershell
Select-String -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Pattern "^6\.\s+\*\*" | Select-Object -First 1
```
Expected: строка вида `6. **Обезличивание для всего...** ...`.

- [ ] **Step 3: Добавить правило #7 после правила #6**

Use Edit tool. Найти текст:
```markdown
6. **Обезличивание для всего, что пушится в claude-base**
```

И сразу после блока правила 6 (до закрывающего `---` или начала следующей секции) добавить:

```markdown
7. **Нормы — только через `norm-lookup`.** Локальная библиотека норм
   лежит в `~/.claude/library/` (INDEX.md + categories) + PDF на Я.Диске
   (расшарена владельцем). **Не цитировать** ГОСТ/СП/СНиП/ПУЭ/постановления
   по памяти. Любая нормативная ссылка → делегация в `norm-lookup` агента
   для точной цитаты + пункта + редакции. См. `library/README.md`.
```

- [ ] **Step 4: Verify правило #7 на месте**

Run:
```powershell
Select-String -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Pattern "^7\.\s+\*\*Нормы" | Select-Object -First 1
```
Expected: одна строка с правилом 7.

- [ ] **Step 5: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add CLAUDE.md
git commit -m "feat(CLAUDE): правило #7 - нормы только через norm-lookup агента"
```

---

### Task 6: CHANGELOG.md — notification для сотрудников

**Files:**
- Modify: `~/.claude/CHANGELOG.md`

- [ ] **Step 1: Добавить новую запись в начало CHANGELOG.md**

Use Edit tool. Найти первую секцию `## YYYY-MM-DD` и вставить ПЕРЕД ней:

```markdown
## 2026-05-26 — Knowledge library (база ГОСТ/СП/СНиП)

### Добавлено

- **`library/`** — каркас локальной библиотеки нормативных документов
  (INDEX.md + 8 категорий + README). Закрывает класс ошибок 2026-05-25
  (выдумывание норм по памяти агентами).
- **`scripts/Set-LibraryRoot.ps1`** — per-PC setup helper.
- **`agents/norm-lookup.md`** — расширен под библиотеку: добавлены
  mcp__pdf-mcp + mcp__word read-only tools, алгоритм поиска по INDEX,
  10 структурированных failure modes (`NO_CONFIG`, `NO_INVITE`,
  `SYNC_IN_PROGRESS`, `NOT_IN_INDEX`, `NOT_DOWNLOADED`, и др.).
- **`CLAUDE.md` правило #7** — «нормы только через `norm-lookup`».
- **Spec:** `docs/superpowers/specs/2026-05-26-knowledge-library-design.md`.

### Сотруднику сделать (one-time setup)

После следующего auto-pull:

1. **Принять invite** от Daniil на папку `Claude_Library` в веб-интерфейсе
   Яндекс.Диска (раздел «Доступы»).
2. **Дождаться окончания первичного sync** Яндекс.Диск-клиента
   (10-30 минут в зависимости от размера библиотеки).
3. **Запустить helper:**
   ```powershell
   & "$env:USERPROFILE\.claude\scripts\Set-LibraryRoot.ps1"
   ```
   Скрипт спросит полный путь до Claude_Library на твоём ПК. Подсказка:
   default — `C:\Users\<имя>\YandexDisk\Claude_Library`, но если папка
   shared — Я.Диск может назвать её с префиксом «От Даниила» или
   похожим. Введи полный путь до неё.
4. **Restart Claude Code** — чтобы агент `norm-lookup` подхватил новые
   tools.

После этого любой нормативный запрос (например «что говорит ГОСТ 21.101
про штамп»?) будет автоматически идти через `norm-lookup`, который
вернёт **дословную цитату** из PDF + номер пункта + редакцию.

### Backward compat

Пока библиотека не наполнена — `norm-lookup` будет возвращать failure
mode `NOT_IN_INDEX` и пробовать WebFetch cntd.ru. По мере добавления
норм Daniil'ом — всё больше запросов будет обслуживаться локально.

---

```

- [ ] **Step 2: Verify запись на месте**

Run:
```powershell
Select-String -Path "$env:USERPROFILE\.claude\CHANGELOG.md" -Pattern "2026-05-26 — Knowledge library" | Select-Object -First 1
```
Expected: одна строка с найденной записью.

- [ ] **Step 3: Commit**

```powershell
cd $env:USERPROFILE\.claude
git add CHANGELOG.md
git commit -m "docs(CHANGELOG): запись 2026-05-26 knowledge library + инструкция сотрудникам"
```

---

### Task 7: Push всех коммитов + smoke test всей цепочки

**Files:** нет правок, только проверка.

- [ ] **Step 1: Проверить состояние git**

Run:
```powershell
cd $env:USERPROFILE\.claude
git log --oneline -10
git rev-list --left-right --count HEAD...origin/main
```
Expected: 6 новых коммитов локально (Tasks 1-6), `ahead 6 / behind 0`.

- [ ] **Step 2: Push в origin**

Run:
```powershell
cd $env:USERPROFILE\.claude
$env:GIT_TERMINAL_PROMPT = '0'
git -c http.proxy="" -c https.proxy="" push origin main
```
Expected: `Х..Y main -> main` без ошибок, exit 0.

- [ ] **Step 3: Verify на GitHub через API**

Run:
```powershell
$env:HTTPS_PROXY = ""
$resp = Invoke-RestMethod -Uri "https://api.github.com/repos/K7-LS/claude-base/contents/library" -Headers @{Accept='application/vnd.github+json'}
$resp | Select-Object name, type | Format-Table
```
Expected: список с `README.md`, `INDEX.md`, `categories` (директория).

- [ ] **Step 4: Smoke test — все компоненты на месте**

Run:
```powershell
$ok = $true
$paths = @(
    "$env:USERPROFILE\.claude\library\README.md",
    "$env:USERPROFILE\.claude\library\INDEX.md",
    "$env:USERPROFILE\.claude\library\categories\spds.md",
    "$env:USERPROFILE\.claude\library\categories\ov.md",
    "$env:USERPROFILE\.claude\library\categories\vk.md",
    "$env:USERPROFILE\.claude\library\categories\eo.md",
    "$env:USERPROFILE\.claude\library\categories\ss.md",
    "$env:USERPROFILE\.claude\library\categories\ppr.md",
    "$env:USERPROFILE\.claude\library\categories\prikazy.md",
    "$env:USERPROFILE\.claude\library\categories\shablony.md",
    "$env:USERPROFILE\.claude\scripts\Set-LibraryRoot.ps1",
    "$env:USERPROFILE\.claude\.library-config.json"
)
foreach ($p in $paths) {
    if (Test-Path $p) { Write-Output "OK   $p" } else { Write-Output "MISS $p"; $ok = $false }
}
if ($ok) { Write-Output ""; Write-Output "All artifacts present." }
```
Expected: 12 строк `OK`, финальная `All artifacts present.`

- [ ] **Step 5: Verify CLAUDE.md правило #7 и agent norm-lookup tools**

Run:
```powershell
Select-String -Path "$env:USERPROFILE\.claude\CLAUDE.md" -Pattern "^7\..*norm-lookup" | Select-Object -First 1
Select-String -Path "$env:USERPROFILE\.claude\agents\norm-lookup.md" -Pattern "^tools:" | Select-Object -First 1
```
Expected: правило #7 видно + tools строка содержит `mcp__pdf-mcp`.

- [ ] **Step 6: Финальное сообщение пользователю**

После прохождения smoke test'а 1-5 успешно — сказать пользователю:

> «Knowledge library инфраструктура раскатана. Что сделать сейчас вручную:
>
> 1. **Создать `Claude_Library/` в твоём 1ТБ Я.Диске** (если ещё не создано — Set-LibraryRoot уже мог создать; проверь).
> 2. **Расшарить через веб-интерфейс Я.Диска** → «Доступы» → invite каждому из 8 сотрудников **на чтение**.
> 3. **Restart Claude Code** на DANIILPC — чтобы norm-lookup подхватил новые tools.
> 4. **Положи первую тестовую норму** в `<YandexDisk>/Claude_Library/spds/` (например ГОСТ 21.101) — и добавь строку в INDEX.md.
> 5. **Smoke test E2E:** `Agent(subagent_type="norm-lookup", prompt="что говорит ГОСТ 21.101 про штамп?")`. Ожидаемый ответ — структурированный с цитатой + пунктом + достоверностью `locally_read_PDF`.»

---

## Self-Review Summary

**1. Spec coverage:** ✓ Все требования spec покрыты:
- Файловая структура (Task 1)
- gitignore для config (Task 2)
- Set-LibraryRoot helper (Task 3)
- norm-lookup расширение tools + algorithm + failure modes (Task 4)
- Правило в CLAUDE.md (Task 5)
- CHANGELOG notification + инструкция сотрудникам (Task 6)
- Раскатка + smoke test (Task 7)

**2. Placeholder scan:** ✓ Все шаги содержат конкретный код / команды / expected output. Никаких TBD / TODO / «fill in».

**3. Type consistency:** ✓ `library_path` используется одинаково везде (Task 3 пишет, Task 4 algorithm читает). 8 категорий одинаковые во всех местах (Task 1 создаёт каркас, Task 3 helper, Task 4 algorithm). Failure modes одинаковые в Task 4 algorithm и spec.

**4. Scope check:** ✓ Один связный feature, не нужно дробить.
