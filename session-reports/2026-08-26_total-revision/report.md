# Тотальная ревизия базы — 2026-08-26

Метод: четыре параллельных read-only разведчика (scripts+hooks, skills, agents/chains/blocks/core, инфраструктура) по HEAD `65c3779`, затем точечный ремонт бесспорных поломок. Решения по среде Codex — за самим Codex (поручение владельца), решения об удалениях — за владельцем.

## 1. Починено в этой сессии

| Что | Было | Стало |
|---|---|---|
| `codex-layer/capability-registry.json` | role_id «сметчик»/«снабженец» кириллицей, синк падал на каждом Edit/Write с 25.08 | `smetchik`/`snabzhenets`, ролевой этап проходит |
| `~/.codex/agents/` | 4 TOML на 2 роли → warning «duplicate agent role name» при каждом старте Codex | кириллические файлы → `*.bak-dedup`, 16 TOML |
| `codex_sync.py:311` + тест | жёсткий инвариант «11 enable / 26 skip» — любое добавление скилла ломало синк | зеркальность манифеста без замороженных чисел; тесты 6/6 |
| `codex-layer/skills-manifest.json` | 4 скилла не классифицированы (codex-bridge, document-quality-gate, ru-writing-style, sync-base) | классифицированы skip (черновик — на вердикте Codex) |
| `graphify-out/.graphify_python` | мёртвый путь к venv `graphifyy` → 216 подряд `REBUILD-FAILED` с 2026-08-06 | указатель удалён, хук на системном `python`, `REBUILT-ok` |
| Наблюдаемость моста | — | журнал `interop/dialog.md` + страница :7343 + скилл `codex-bridge` (коммит `65c3779`) |

## 2. Сломано, ждёт решения владельца

1. **Хуки project-memory в пустоту.** `settings.shared.json:75,116,148` → `skills/project-memory/tools/hooks/session_{start,end}.ps1` — файлов нет (потеряны при реворке?). Решение: восстановить хуки или убрать из shared.
2. **Тест-сьюты снесены auto-sync'ом `5577c3a` (2026-08-10)**, документация жива и ссылается на них: supervisor («29 passed» — тестов нет), web-access (3 ссылки + удалённые `doctor.py`, `yt_subs.py`), project-memory. Решение: восстановить из git-истории или вычистить упоминания.
3. **Контур feedback раздвоен:** `.feedback-config.json` → `daniileliseev1337/claude-base-feedback`, а `Update-ClaudeBase.ps1:185` и `pull-feedback.ps1` → `K7-LS/claude-base-feedback`. Новые consumer'ы и старые ПК будут писать в разные репо.
4. **Три репозитория в одной базе:** origin → `daniileliseev1337/claude-base` (редирект на K7-LS работает), релизы → `K7-LS/claude-base-v2`, README → `K7-LS/claude-lite-instaler`. `base/MIGRATION-SOURCE.json`: `migration_status: IN_PROGRESS` с 2026-08-06. Решение: переключить origin, закрыть миграцию.
5. **`screenshot-source-zoom.ps1`** — matcher `screenshot|zoom` не совпадает ни с одним живым инструментом с 2026-07-09 (эпоха playwright). Анти-паттерн A11.1 не инжектится. Обновить matcher или убрать хук.
6. **`mcp-manifest.json` потерял пины `mcp<2`** для fetch/time/Revit-Connector (реальный `.claude.json` их держит): переустановка `setup-extras.ps1` на любом ПК затащит SDK 2.x и сломает серверы. Плюс: нет `codex`, лишний `mineru`, `last_updated: 2026-07-02`.
7. **`library/` мертва как канал:** `.library-config.json` не создан → `norm-lookup` молча уходит в веб вместо локальных норм. PDF на Я.Диске живы (`Yandex.Disk-deliseev@k-7.tech\Claude_Library`). Прогнать `Set-LibraryRoot.ps1`; приёмка `_на_проверку_2026-06-02` не закрыта 3 месяца.

## 3. Документы, которые врут (переписать или убить)

- **README.md** — состояние 2026-07-07: «15 агентов» (их 16, имена другие), «16+ скиллов» (их 41), «CLAUDE.md ~10 KB» (1,7 КБ), «9 MCP» (15).
- **CHANGELOG.md** — последняя запись 2026-07-07; мимо прошли base v2, codex-layer, реворк project-memory, мост.
- **«Карта vault.md» / vault-hub.md** — Obsidian-эпоха, битые ссылки, last-verified 2026-05-18.
- **graph.json / GRAPH_REPORT.md** — 2026-06-23: 11 несуществующих файлов в графе, 107 новых не покрыто (skeleton теперь свежий, полный граф — нет).
- **CLAUDE.md** — «локальные изменения обратно не отправляются» при живом двустороннем auto-push на этом ПК; ни слова про `memory/` (12 агентов её читают) и про chains/blocks (потеряны точки входа).

## 4. Раздвоенные источники правды

- `core/AGENTS.core.md` (12,6 КБ) читает **только Codex**; Claude живёт на CLAUDE.md 1,7 КБ — целые разделы правил существуют для одной стороны. Бэкап старого полного CLAUDE.md: `CLAUDE.md.bak-pre-core` (22 КБ).
- `memory/` (63 файла) ↔ `base/cold/memory/` (20 копий + уникальный `reference_officecli.md`) — разошлись.
- `chains/` (5) ↔ `base/cold/chains/` (3, две разошлись) — а механизма запуска цепочек нет нигде.
- `skills/sync-base` ↔ `base/control-skills/sync-base` (старая копия, другой репо и протокол).

## 5. Мёртвый вес (кандидаты на удаление — решает владелец)

| Объект | Объём | Доказательство смерти |
|---|---|---|
| `mcp-servers/autocad-mcp/.venv.bak-codex-exp` + `.venv.broken-before-codex` | **322 МБ** | май 2026, ни одной ссылки |
| `scripts/graphify-out/`, `scripts/__pycache__`, `scripts/.pytest_cache` | ~МБ | застыли 2026-06-08, дублируют корневые |
| 7 правил .gitignore на дизайн-скиллы | — | все 7 папок отсутствуют на диске, заменены плагинами |
| `skills/local-video-digest` | 12 КБ | ffmpeg и faster_whisper не установлены — обе половины конвейера |
| `skills/revit-family-generator` | 61 КБ | собственный README: «наш executor его заменил и превзошёл» |
| `codex_context_governor.ps1` | — | не подключён ни к одному hooks-событию |
| `vault-hub.md`, «Карта vault.md» | — | Obsidian-эпоха, битые ссылки |
| `evals/` | — | последний реальный прогон 2026-05-20, покрыт 1 скилл из 41 |
| 5 `memory/backlog_*.md` | — | не тронуты с июня |

## 6. Дубли скиллов (решить границы или слить)

- word-helper ↔ word MCP ↔ anthropic-skills:docx; excel-helper ↔ excel MCP ↔ anthropic-skills:xlsx; pdf-edit+doc-extract ↔ pdf-mcp ↔ anthropic-skills:pdf ↔ pdf-viewer (ценность локальных — правила оформления, не маршрутизация).
- handoff-to-new-chat ↔ llm-interop ↔ codex-bridge (~390 строк на одну тему).
- structured-artifacts ↔ project-memory ↔ facts-layer («выноси состояние в md» ×3).
- skill-development ↔ superpowers:writing-skills ↔ anthropic-skills:skill-creator (один триггер ×3).
- web-access ↔ WebFetch/WebSearch/exa/fetch; doc-finder ↔ supplier-due-diligence; понемногу: karpathy↔superpowers, understanding-map↔brainstorming.

## 7. Прочая гниль (мелочь, чинится по ходу)

Битые ссылки на memory (graphify ×3, web-access, karpathy `cases/`); недообезличенность (`K7 signed COM PDF exporter` — инструмент-призрак в document-quality-gate; `<организация>` в операционном тексте chains-pattern); `skills/skills.md` (индекс) удалён 2026-08-22 вместе с генератором без точки вызова; `aggregate-tool-usage.ps1` и `build_skills_index.py` «вызываются хвостом /sync-base», который их не вызывает; local-osint-recon помечен «личный, не переносить», но трекается git; шаблон агента v1.0 отстал от формата (нет capability-слоя); `base/STATUS.json` `PROGRAM_RELEASE 0/3` ↔ `sync-policy.json` «2/3».

## 8. Зона Codex — вердикты получены через мост и применены

Тред `01a03e71-bd01…`. Вердикты Codex и исполнение:

1. **ru-writing-style → enable**, остальные три skip — применено (манифест + реестр).
2. **Вариант (а):** все 15 MCP-серверов удалены из top-level `config.toml`, живём по whitelist (`codex_sync mcp on/off`); `claude` и `node_repl` сохранены. Бэкап: `config.toml.bak-revision-20260826`. Побочно ушёл `[shell_environment_policy.set]` c машинным ключом `NODE_REPL_TRUSTED_BROWSER_CLIENT_SHA256S` (приложение восстановит при необходимости).
3. **force-overwrite разрешён** — AGENTS.md (канон, +2 недели правок), 16 TOML ролей, 9 junction-скиллов; разошедшиеся копии папок сохранены в `~/.agents/skills/_bak-revision-20260826/`. `hooks.json` не тронут (журнальный хук моста) — единственный оставшийся manual-drift, осознанный.
4. **Эталон base.toml принят:** `[agents] max_threads=6, max_depth=1` и остальные секции теперь в managed-блоке.
5. **`*.bak-dedup` удалены.**

Смоук после применения: старт Codex без warning'ов про дубли ролей и без Auth-ошибки exa; расход старта упал с ~23,5k до ~15,3k токенов. Codex-приложению нужен перезапуск, чтобы подхватить новый config.toml.

## 9. Предлагаемый порядок работ

1. ~~Разблокировать синк и навигатор~~ — сделано сегодня.
2. Вердикты Codex → применить (п. 8).
3. Решения владельца по п. 2 (сломанное) и п. 5 (kill list).
4. Один день «документов правды»: README, CHANGELOG, CLAUDE.md (вернуть memory/chains/blocks или похоронить chains/blocks осознанно), mcp-manifest с пинами, единый feedback-репо, origin → K7-LS.
5. Слияние дублей скиллов (п. 6) — по одному решению на группу, с переносом ценного (правила оформления) в выжившего.
6. Закрыть миграцию base v2 (`MIGRATION-SOURCE.json`, счётчики STATUS).
