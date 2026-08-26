# Claude-канал: разблокировка, инцидент и незакрытые вопросы

Сессия 2026-08-21, DANIILPC. Отчёт составлен 2026-08-24.
Проект: «Заведомо проигранный бой (или нет)», ядро — `0_СТАТУС_программы.md`,
слой сессии — `Claude/STATUS.md` и `Claude/ЖУРНАЛ СЕССИЙ.md`.

## TL;DR

Claude-канал был полностью заблокирован: ни один релиз не верифицировался и
база не устанавливалась. Причина — не один баг, а потерянная ветка плюс три
независимых гейта. Выпущены `claude-v0.1.13…0.1.16` и Foundation `0.5.6`,
`0.5.7`; на consumer стоит `0.1.16`, doctor `CANONICAL`. По дороге вскрыт и
исправлен критический дефект отката Foundation, из-за которого неудачная
установка разрушила живой профиль.

## Что закрыто

### Канал верификации

Релизы, выпущенные до переноса в `K7-LS`, не проходят `gh release verify`:
GitHub Release Attestation не перепривязывается к новому owner, а rerun
workflow этого не меняет. Выпуск нового релиза **из организации** решает
проблему штатно — bridge, как для Codex, не понадобился.

Выпущено и верифицировано (immutable, `verify` + `verify-asset` +
`attestation verify` по каждому ассету):

| Релиз | Содержание |
|---|---|
| `claude-v0.1.13` | первый канонический выпуск из K7-LS |
| `claude-v0.1.14` | сняты три гейта установки |
| `claude-v0.1.15` | перепривязка к Foundation 0.5.7 |
| `claude-v0.1.16` | восстановлен канонический namespace |
| `foundation-engine-v0.5.6` | `.js` в legacy session-tools |
| `foundation-engine-v0.5.7` | rollback восстанавливает свой snapshot |

### Три гейта, блокировавшие установку

1. **`RELEASE_INTEGRITY` недостижим конструктивно.** Evidence пишется до
   публикации, attestation появляется при публикации, ассеты после неё
   immutable — вердикт навсегда оставался `PENDING_PUBLICATION`, а политика
   требовала `PASS`. Убран из `required_verdicts`: consumer и так выполняет
   `release verify`, `verify-asset` и `attestation verify` первыми руками.
2. **Контракт команд Foundation разошёлся.** 0.5 добавил `apply` (шесть
   команд), consumer принимал ровно пять. Базы `0.1.11`–`0.1.13` собраны под
   0.5.x и не могли установиться собственным sync-base.
3. **Runtime делал лишнее.** `plan → install → doctor` свёрнут в один
   `install`.

### Дефект Foundation: `.js`

Валидатор типов файлов знал `.lsp`, `.patch`, `.ps1`, `.py`, но не `.js`.
Единственный файл `id-tom-priemka/tools/priemka_workflow.js` заваливал весь
установленный state как `INVALID_PACKAGE` и блокировал любую установку на
baseline из 34 скиллов. Именно поэтому набор session-tools когда-то схлопнули
до одного `ru-writing-style` — там только `.md`.

### Критический дефект отката (0.5.7)

Snapshot записывает `.llm-foundation/state/session-tools/<target>/state.json`
— состояние, которое install собирается заменить; схема 4 этот путь
разрешает. Но `existed` валидировался без флага `-AllowSessionState`, и
rollback отвергал снимок, только что созданный install-ом (`UNSAFE_PATH`).

Так как install сносит managed-поверхность **до** записи новой, автооткат —
единственный путь назад. На любом профиле с session-tools state этого пути не
существовало.

Проявилось вживую: установка `0.1.14` опустошила 34 managed-пути (16 агентов,
3 команды, `base/cold`, `base/runtime`, `base/foundation`, 29 скиллов),
автооткат ответил `RECOVERY_REQUIRED`. Профиль восстановлен вручную из
snapshot `20260821T142931Z-48c181c9…` — сверка побайтово, 0 расхождений.
После 0.5.7 тот же snapshot откатился штатно (`ROLLED_BACK`).

Покрыто тестом `test_rollback_accepts_snapshot_holding_session_tools_state`
в `tests/test_foundation_shared_tools.py`: ставит, обновляет, проверяет что
путь реально попал в снимок, откатывает. Красный без фикса.

### Связка Claude ↔ Codex

Отдельного плагина не существует — связь делается штатными MCP-режимами:

- Claude → Codex: `claude mcp add codex -s user -- codex mcp-server` (`✓ Connected`).
- Codex → Claude: `codex mcp add claude -- claude.exe mcp serve`, запись легла
  в `~/.codex/config.toml` строкой 201 — **вне** managed-блока
  `claude-base managed` (281–283), поэтому `codex_sync.py` её не затрёт.
- В `codex-layer/mcp-whitelist.json` `codex` намеренно **не** добавлен, иначе
  синк пробросил бы Codex сам в себя.

## Корневая причина «многое не работает»

Релизы `claude-v0.1.9` (774e8c3) и `claude-v0.1.10` (82fd33d) выпускались с
ветки `codex/project-memory-unified`, которая **никогда не сливалась в main**.
С `0.1.11` (eb36bc0) выпуск переключился на `main` — и это был откат семи
коммитов:

```
82fd33d perf: make Claude sync a single install
774e8c3 feat: simplify Claude base updates
64759a3 fix: separate Claude session skill ownership
79e618e feat: auto-update portable Claude skills
57c5d71 feat: share one project memory core
c1db2f7 fix: remove retired skills from catalog
7a157ef feat: retire legacy Claude-bound skills
```

В ветке уже было то, что просили сделать заново: `MAX_TOOLS = 64`,
автообнаружение всех скиллов, пустой `required_verdicts`, единое ядро
project-memory, один `install`.

**Ветка красная сама по себе** — её multi-tool апдейтер (до 64 tools)
противоречит её же тестам, требующим ровно один. Вероятно поэтому её и не
слили. Целиком тащить нельзя: после ручной сборки правильной комбинации
оставалось 16 падений, а тесты ветки ещё и ждут 38 скиллов против 39 в main.

Взята только самодостаточная часть: `control-skills/sync-base` (политика +
один install) плюс фикс контракта команд.

## Состояние на конец сессии

**Consumer `~/.claude`:**
- `base/VERSION` = `0.1.16`, движок `0.5.7`, doctor `CANONICAL`
- 16 агентов, 3 команды, 40 скиллов
- политика: `repository: K7-LS/claude-base-v2`, `required_verdicts: []`
- `active.json` = 0.1.16 / 0.5.7, `pending.json` отсутствует
- git: только две правки `codex-layer/*`, бывшие до сессии

**Репозитории:**
- `K7-LS/claude-base-v2` main = `49058e3`, чисто
- `K7-LS/llm-foundation-installer` main = `96dcfd3`
- локальный чекаут installer сидит на `fix/workpc-live-vertical-slice-r4` с
  незакоммиченными `src/gui/InstallerApp.cs`, `InstallerEmployeeView.xaml` —
  **это было до сессии, не трогал**

**Вручную приведено в порядок (обходные решения, не механизм):**
- session-tools state пересобран под фактические файлы: 34 tool-записи,
  141 файл. Бэкап — `scratchpad/session-tools-state.json.bak`
- нормализованы CRLF в 5 файлах `project-memory` (расхождение было только в
  переводах строк)

## Незакрытые вопросы

### 1. Multi-tool session tools — в пакет попадает один скилл вместо 34

`tools/session_tools.py` в main: `MAX_TOOLS = 32`, жёсткий дефолт
`tool_ids = ("ru-writing-style",)`, `release_builder` вызывает без аргумента.
В ветке уже написано решение (`MAX_TOOLS = 64` + автообнаружение), и
`runtime/update-session-tools.ps1` там же поддерживает `1..64`.

Что мешает: тест `test_protocol_one_blocks_zero_or_multi_tool_assets_before_mutation`
(в обеих версиях идентичен) требует `BLOCKED_MULTI_TOOL_ASSET` при
`tool_count` 0 или 2. Нужно решить, каким должно быть поведение при
заявленном `tool_count`, не совпадающем с содержимым архива, и переписать
восемь тестов под новую политику.

Побочный эффект выпуска: пакет с 39 tools старые consumer'ы (`0.1.8`–`0.1.12`)
отвергнут с `BLOCKED_MULTI_TOOL_ASSET`, пока не поставят новую базу.

### 2. Унификация project-memory не перенесена

В ветке — единое ядро для Claude и Codex, `core_layout.py`,
`gen_project_agents.py` и хуки сессии. В main хуки намеренно удалены, и их
отсутствие закреплено тестом (`assert not hooks.exists() or not any(...)`,
затем ранний `return`). Тесты ветки ждут 38 скиллов, main содержит 39
(лишний — `document-quality-gate`).

Перенос требует ревизии обеих линий целиком, а не выборочного checkout.

### 3. install не обновляет session-tools state (`PRESERVE`)

`foundation.ps1`, ветка `if (Test-Path $Paths.state_path) { action = 'PRESERVE' }`:
при существующем state install его сохраняет и лишь проверяет, но сами файлы
скиллов заменяет. Запись владения устаревает → doctor `ACTIVE_DRIFT`.

Сейчас обойдено ручной пересборкой state. Механизм надо чинить: либо install
обновляет записи заменённых им файлов, либо state пересобирается из
`session_tools_baseline` пакета.

### 4. OpenCode-канал не разблокирован

`opencode-v0.1.13` (18.08, до миграции) — `gh release verify` **FAIL**, ровно
тот же дефект attestation. Нужен канонический релиз из `K7-LS`, как сделано
для Claude. Codex уже закрыт (`codex-v0.1.26` PASS).

### 5. Ветка `codex/project-memory-unified` остаётся невлитой

Семь коммитов, красная. Пока она висит, риск повторения истории «выпустили с
ветки, потом откатили» сохраняется. Решить: довести до зелёного и слить, либо
осознанно закрыть, перенеся ценное точечно.

### 6. Installer и Launch Center — переработка

Заявлено владельцем 2026-08-21: в текущем виде не работают, чинить точечно не
нужно. Объём переработки не определён.

### 7. Пин клиента разошёлся с реальностью

Контракт пиньован на Claude Code `2.1.218` (SHA `81fcf59b…`), на машине стоит
`2.1.114` (SHA `6f4a961e…`, подпись Anthropic PBC — Valid). По решению
владельца несовпадение теперь предупреждение, а не гейт: canary пишет
наблюдаемую версию и `client_pin.matched: false`, evidence несёт limitation.
Сам пин в `runtime/client-acceptance.json` не обновлён.

### 8. Provider live не проверялся

`CLAUDE_PROVIDER_MARKER` = `NOT_REQUIRED` во всех выпущенных релизах — по
решению владельца provider-гейт вырезан. `POLICY_AUDIT` в `STATUS.json`
остаётся `BLOCKED_REGION_VERIFICATION` с записью про Supported Regions
Policy; `blocked_by` сокращён до одного регионального пункта, добавлено поле
`unverified`.

### 9. `$sync-base` не проходит по сети

Профиль соединения — `Proxy` через `server3.scuf-meta.ru:8443`. TCP проходит,
но загрузка пакета (~13 МБ) рвётся: `proxyconnect` / `wsarecv` / пустой
`BLOCKED`, три попытки подряд. Прямой `gh` в это же время работает.

Обход (применён): скачать ассеты через `gh`, вручную прогнать те же проверки
(`release verify`, `verify-asset`, `attestation verify`, сверка SHA-256 с
манифестом), затем `foundation.ps1 install` с проверенным пакетом. Настройки
соединения владельца не менялись.

### 10. Связка с Codex не проверена в деле

MCP-серверы зарегистрированы с обеих сторон, Claude-сторона отвечает
`✓ Connected`. Реального вызова Codex через MCP и обратного вызова Claude из
Codex не выполнялось.

## Порядок закрытия (предлагаемый)

1. **№3** — install и session-tools state. Самое дешёвое и снимает ручной
   костыль, который иначе придётся повторять при каждом обновлении.
2. **№1** — multi-tool session tools. Разблокирует возврат 34 скиллов;
   начинать с решения по политике `tool_count`, затем тесты.
3. **№4** — OpenCode canonical release. Механика уже отработана на Claude,
   повторяется почти без исследования.
4. **№2 и №5** — project-memory и судьба ветки; логично делать вместе.
5. **№7, №8** — привести пины и вердикты в соответствие решениям владельца.
6. **№6** — Installer и Launch Center, отдельная крупная тема.
7. **№9, №10** — инфраструктура: прокси и проверка связки.

## Полезные факты для продолжения

- Локальные чекауты: `~/repos/claude-base-v2`, `~/repos/llm-foundation-installer`,
  worktree `~/repos/.worktrees/foundation-0.5.5` (ветка `fix/rollback-session-state`,
  уже слита), распакованные движки в `~/repos/.worktrees/foundation-release-0.5.6|0.5.7/engine`.
- Полный локальный suite базы: `LLM_BASE_CI_OFFLINE=1 py -3.12 -m pytest -q`,
  норма — `142 passed, 1 skipped` (skip: symlink creation unavailable).
- Тест `test_busy_target_lock_is_bounded_and_does_not_contact_network` и
  `test_claude_sync_runtime_is_native_and_accepts_semver_client_versions`
  флейкуют под нагрузкой (таймаут), изолированно проходят.
- Релизная цепочка базы: `run_offline_acceptance.py` → `live_canary.py` →
  `final_evidence.py` → `promote_candidate.py` → `gh release create` →
  `release_verifier.py`. `--provider-marker-evidence` теперь опционален.
- Foundation release: `gh workflow run "Windows CI" --ref main -f
  build_public_unsigned=false -f build_foundation_release=true`, затем
  `gh run download <id> --name foundation-engine-<ver>-release`.
- Foundation `_validate_foundation` требует шесть команд:
  `apply,doctor,install,inventory,plan,rollback`.
- Foundation legacy-типы файлов: `.docx .gitkeep .graphify_version .js .lsp
  .patch .ps1 .py .tmpl .xlsx` плюс строгие `.md .json .yaml .yml .toml .txt`.
