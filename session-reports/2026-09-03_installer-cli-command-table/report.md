# Handoff: инсталлятор — этап 1+4, PR-1: таблица команд и тестовый хост (2026-09-03, DANIIL-LAPTOP)

## Актуальный handoff (поздний вечер 2026-09-03) — читать первым
- **Состояние.** main = `e89a1b2` (#70 таблица команд + тестовый хост, #71 версия 0.4.2, #72 README-таблица команд слиты владельцем). Комплект 0.4.2 в синке, canary пройден. Открыты и ждут CI/слияния: **#73** `feat/launch-center-install-shortcuts` (центр запуска в `~/.llm-foundation/launcher` + ярлыки «K7 Launch Center»; 208 passed / 3 skipped локально) и **#74** `chore/codex-cli-0.153.0` (пин Codex CLI 0.153.0; тесты пина обновлены). Worktrees `.worktrees/launch-center-install`, `.worktrees/codex-0.153` оставлены до слияния — потом `git worktree remove` + удалить ветки.
- **Решения владельца за вечер.** Строгость «искать варианты сам, решение, меняющее результат, и любое сомнение/расхождение с ТЗ — пользователю до действия» — для Claude и Codex (`core/AGENTS.core.md`, общие агенты, слой Codex; всё синхронизировано в `~/.codex`). Умолчания агентов не фиксировать (срок КП, дата письма, НДС, аналоги — по ситуации, с вопросом). Launcher — ярлык на синк сделан + фича #73. Codex обновить (#74). Мост — shell через `danger-full-access`.
- **Мост Codex.** MCP `codex` у Claude → комплектный `…/codex-home/packages/standalone/current/bin/codex.exe` (бэкап `~/.claude.json.bak-codex-mcp-20260903`). Read-only sandbox сломан: Store/MSIX `pwsh.exe` под sandbox-пользователем (`CreateProcessAsUserW 5`), лечится Codex ≥ 0.148 → после #74 и установки на ноутбуке проверить `codex exec --sandbox read-only` (ждать в sandbox-журнале `START:` без `WindowsApps`). Бэкенд Codex с 17:44 отвечал 404 на всё (даже `pong`, вход в силе) — не получены: подтверждение `config.toml` после переноса таблиц, маршрут вместо `web-access` для native `norm-lookup`, подтверждение языковой строки. Пакет повторить (`codex-bridge`, full-access, только чтение).
- **Следующие шаги по порядку.** 1) CI #73/#74 → слияние владельцем. 2) Версия 0.4.3 (APP_VERSION + assembly-атрибуты в `InstallerApp.cs`, тест FileVersion RED→GREEN, PR) → слить. 3) Комплект 0.4.3 из main в синк командой из раздела ниже (0.4.2 → `_прежний-2026-09-03-вечер`), диагностика из синка, памятка «Что нового в 0.4.3» (центр запуска в профиле и ярлык; Codex 0.153.0). 4) Узкий canary: ярлык «K7 Launch Center» на рабочем столе станции, версия Codex после установки. 5) Проверка read-only sandbox моста на ноутбуке; повтор пакета Codex. 6) Точка хешей для диагностики (дизайн ниже). 7) Этап 1 (155 текстовых ассертов → behavior).
- **Промпт для нового чата.** «Продолжение реворка инсталлятора (DANIIL-LAPTOP). Прочитай `rework-bases/Claude/STATUS.md`, верх журнала и отчёт `~/.claude/session-reports/2026-09-03_installer-cli-command-table/report.md` (раздел «Актуальный handoff»). Проверь CI и статус PR #73 и #74; если слиты — версия 0.4.3, комплект в синк, диагностика, попроси владельца о canary. Решения, меняющие результат, — только через владельца; варианты искать самостоятельно. Не переключать ветку под фоновым pytest; параллельные PR — через git worktree; `K7_OFFICECLI_BINARY_PATH=$HOME/repos/.officecli-cache/officecli.exe`; итог прогона — по строке pytest; скрипты и коммиты — файлом, не heredoc.»

## Дизайн следующего PR этапа 4: точка хешей для диагностики (не начат)
- Источники внутри EXE: движок — ресурсы `foundation.ps1` + `engine-manifest.json` (`foundation_ps1_sha256`, `protocol_version`; `BundleIntegrity.ValidateEngine`, `ReadResourceBytes`); пакеты — индекс `TrustedPackages.json` (записи `resource_name`, `sha256`, `bytes`, относительный путь; `ProductCatalog.LoadTrustedPackages`, проверка в строках ~418–440). Диагностика сейчас привязывает отчёт только к SHA EXE и манифесту (`bundle.exe_sha256`, `exe_matches_manifest`); `packages[]` без хешей.
- Точка `--bundle-hashes-json` (tool, 0 аргументов): `{exe_sha256, engine: {protocol_version, foundation_ps1_sha256, engine_manifest_sha256, embedded_valid}, packages: [{id, sha256, bytes, validated}]}`; регистрация в `InstallerCommands`, строка в README-таблице (гейт полноты подхватит), RELEASE_COMMANDS → 11.
- `worksite-diagnostics.ps1`: `Invoke-BundleJson 'hashes' @('--bundle-hashes-json')` → поле `hashes` в отчёте (schema 2, additive), fail-closed при отсутствии ответа; `test_worksite_diagnostics.py` — поле и разбор в 5.1/pwsh.
- Тесты: на shared-бандле — 64-hex, `embedded_valid` true, три id; на бандле с пакетами (`_accepted_foundation` в test_gui) — `validated` true и sha == sha256 файла пакета из package root; `exe_sha256` == sha EXE.
- После слияния — версия 0.4.3, комплект в синк, узкий canary (EXE меняется).

## Дополнение 4 (вечер, ответ Codex №3 и расчистка)
- Read-only sandbox Codex: причина — Store/MSIX `pwsh.exe` под sandbox-пользователем (`CreateProcessAsUserW 5`), upstream openai/codex#35871, исправлено с 0.148; у нас 0.146.0-alpha.3.1. Ждёт решения владельца (обновить комплектный Codex / не-MSIX PowerShell 7 / оставить full-access).
- `codex_sync.py`: перенос таблиц канона из-за пределов managed-блока внутрь (`_table_sections`, `_strip_tables`, `_managed_matches_with_outside_tables`); тесты 83/83, golden обновлён (`UPDATE_GOLDEN=1`); реальный `~/.codex/config.toml` приведён (бэкап `.bak-relocate-20260903`), `check` чистый. `LANG_LINE` — латиница или гибрид.
- Профили дочищены под новую границу: `kp-writer`, `letter-writer`, `pto-engineer` (структура, плейсхолдеры, путь — по решению пользователя). Открыто для владельца: срок КП, дата письма, НДС, аналоги. Codex запрошен про маршрут вместо `web-access` в native `norm-lookup` и про проверку конфига.
- CI #72 зелёный — ждёт слияния владельцем. PR-1 фичи Launcher — после «да» владельца на дизайн.
- Мост 17:44–17:49: три вызова Codex подряд оборвались `404 Not Found` от `chatgpt.com/backend-api/codex/responses` до первого токена (сбой бэкенда/сессии Codex, не пакета). Не получены: подтверждение конфига после переноса таблиц, маршрут вместо `web-access` для native `norm-lookup`, подтверждение языковой строки. Повторить пакет позже (суть — три пункта выше). Проверено 17:52: `codex login status` — «Logged in using ChatGPT», но даже `codex exec "pong"` без shell даёт тот же 404 после 5 переподключений — недоступен сам бэкенд Codex (или эндпоинт alpha-сборки 0.146), не мост и не логин. Ещё один аргумент за обновление комплектного Codex.

## Дополнение 3 (вечер, после «оба, да, canary сделал»)
- Canary 0.4.2 пройден (отчёты 17:14/17:15: OK, SHA `0f8e7013…`). Ярлык «K7 Launch Center» перенацелен на EXE 0.4.2 в папке синка (`--launch-center-ui`, cwd = синк); старый ярлык (на локальную копию 0.4.0) сохранён в scratchpad сессии, папка `<профиль>\K7-AI-Launcher` не тронута.
- Мост: решение — shell-вызовы через `danger-full-access`; скилл `codex-bridge` обновлён (пинг/грабли). Codex получил пакет: причина `CreateProcessAsUserW 5`, `manual-drift config.toml#managed`, подтверждение новой границы — ответ ждёт (фоновый агент, полный доступ, только чтение).
- PR #72 — README «Команды EXE» (10 команд: кто использует, аргументы, назначение) + гейт `test_readme_command_table_matches_release_surface` (RED → GREEN). Worktree `.worktrees/readme-commands` до слияния.
- Дальше: дизайн фичи «установка центра запуска + ярлыки» (решения владельца: место установки, ярлыки, обновление) → PR; точка хешей движка/пакетов → комплект 0.4.3 + canary.

## Дополнение 2 (после решений владельца, вечер)
- #71 слит владельцем, main = `702fd0e`. Комплект **0.4.2** собран (`.work/release/employee-0.4.2`, FileVersion 0.4.2.0, SHA `0f8e7013edbc6930…`) и выложен в синк; 0.4.1 → `_прежний-2026-09-03-день`; диагностика из синка OK, 7/7; памятка «Что нового в 0.4.2». Ждёт узкого canary на станции.
- Владелец: строгость для Claude и Codex — «искать варианты можно сколько угодно, принятие решения, меняющего результат, и любое сомнение/расхождение с ТЗ — пользователю до действия». Применено: `core/AGENTS.core.md` (абзац про самостоятельность), общие агенты `kp-writer`/`letter-writer`/`smetchik`/`snabzhenets` (структура, плейсхолдеры, путь — по решению пользователя), слой Codex (bootstrap с вопросом, пороги в `pto-engineer`/`norm-lookup`). Всё синхронизировано в `~/.codex`; `codex_sync check` показывает manual-drift `config.toml#managed` (не наше — вопрос Codex).
- Мост: повторный пинг подтвердил `codex-windows-sandbox-setup.exe: program not found`. MCP `codex` перерегистрирован на `<профиль>\.llm-foundation\clients\codex-cli\codex-home\packages\standalone\current\bin\codex.exe` (бэкап `~/.claude.json.bak-codex-mcp-20260903`; действует с новой сессии). С комплектным exe read-only sandbox всё равно падает: `CreateProcessAsUserW failed: 5 (Отказано в доступе)`; `danger-full-access` работает. Решение владельца: мостовые вызовы с shell — full-access сейчас, read-only чинить на стороне Codex.
- Launcher владельца: ярлык «K7 Launch Center» на рабочем столе → `<профиль>\K7-AI-Launcher` (Employee 0.4.0 от 31.08, старая раскладка с `engine/`); в `Desktop\К-7` — InternalUnsigned 0.3.0. Новые сборки локально не устанавливаются, ярлык не создают, запуск — `.cmd` из папки синка. Решение владельца: ярлык на синк сейчас и/или фича «установка лаунчера с ярлыком» (стадия 3, шаг «Готово» = центр запуска).

## Дополнение вечера (после ответов владельца)
- Canary 0.4.1 пройден (отчёты 16:00/16:05, OK); #70 слит владельцем, main = `6760064`, CI зелёный; worktree и ветка убраны.
- Решения владельца по Codex: ожидание бессрочное; все влияющие решения через пользователя. Правило вписано в `codex-layer/AGENTS.codex.md` (раздел «Вопросы владельцу посреди задачи»), хук `codex-autosync` синхронизировал `~/.codex/AGENTS.md` (16:10). Codex уведомлён через мост (тред потерян после рестарта MCP → `codex_deliver.py`). Владельцу: перезапустить Desktop.
- PR #71 — версия 0.4.2 (APP_VERSION + assembly-атрибуты), ждёт слияния. После слияния: комплект 0.4.2 из main в синк командой из раздела ниже (прежний 0.4.1 → `_прежний-2026-09-03-день`), диагностика, памятка «Что нового в 0.4.2», узкий canary.
- Открытый вопрос владельцу: разрешить ли Claude сливать зелёные PR этапа самостоятельно (пока сливает владелец).

## TL;DR
- PR #70 (черновик; не сливать до upgrade-canary 0.4.1): `InstallerApp.Main` → таблица `InstallerCommands`; 42 test-only точки — `InstallerTestHost.cs` под `#if K7_TEST_HOOKS`; `build-gui.ps1 -TestHooks`; точка `--commands-json`; гейт `tests/test_cli_surface.py`. Локально 238 passed / 3 skipped (9 модулей, 17:45), CI run 33750556237 зелёный (PS7 + PS5.1). Ветка `refactor/cli-command-table-test-hooks`, worktree `.worktrees/cli-test-host`, коммиты 878167d (таблица) и d51ae2e (флаг + гейт).
- Codex через мост (тред `01a066f8-d7b2-72a3-a33f-b3ba2eeecf7d`) дал вердикт по вопросам пользователю — `rework-bases/отчёты/2026-09-03-codex-вопросы-пользователю-вердикт.md`; применение ждёт двух решений владельца (бессрочное ожидание vs ~60 мин; отмена низкорисковой автономии).
- Разведки: флейк `reacquire_code 20` (шаг 0 — `reason` в ассерт; фикс только по reason) и PATH детектора версии (наследует окружение; ключ `"opencode"` ≠ `"opencode-cli"` — отдельный дефект).
- Проверено на старте: #65–#69 смержены, main 26a6f03, CI main зелёный, комплект 0.4.1 в синке (12:26), canary с рабочего ПК не приходил (отчёт 12:27 — самопроверка из синка), комментарии с итогом широкого прогона в #68/#69 уже были.

## Источник истины (cascade)
- План с секцией «Исполнение 2026-09-03» (дополнена PR-1, PATH, флейком): `rework-bases/отчёты/2026-09-02-installer-переработка-план.md`.
- План PR-1 в репозитории: `docs/superpowers/plans/2026-09-03-cli-command-table-test-hooks.md`.
- Журнал/STATUS: `rework-bases/Claude/` (верхняя запись — 2026-09-03 вечер).
- Классификация точек: `rework-bases/отчёты/2026-09-03-installer-cli-точки-классификация.md`.

## Дизайн PR-1 (для ревью)
- `InstallerCommands.cs`: `Register(name, kind, min, max, handler)`; `TryRun(edition, bundleRoot, args, out exitCode)` → false = «Неподдерживаемая команда», код 2 (как раньше при неизвестной команде или неверной арности); `ContinueToUi = -1` для `--launch-center-ui`; обработчик `(edition, bundleRoot, args)`, `args[0]` — имя команды.
- Виды: product (`--system-proxy-watchdog`), tool (9, включая новую `--commands-json`), test (42). Арность взята из прежних проверок `args.Length`.
- `InstallerTestHost.cs` целиком под `#if K7_TEST_HOOKS`, регистрация через `static partial void RegisterTestHost()`; csproj: `K7_TEST_HOOKS` только при `K7TestHooks == 'true'`.
- Тесты: `-TestHooks` в 25 прямых вызовах build-gui и в `_build_shared_bundle(test_hooks=True)`; фикстура `release_bundle` (без флага). `build-edition.ps1` флага не имеет — статический гейт.
- Единственный текстовый ассерт на ветку Main переведён на форму регистрации: `tests/test_latest_base_updater.py:66`.
- Тела обработчиков переносил генератор (диапазоны строк из `git show HEAD:src/gui/InstallerApp.cs`, пере-отступ) — при спорах о «дословности» сверять `git diff 26a6f03..878167d`.

## Что дальше (по порядку)
1. Canary 0.4.1 на станции (владелец/сотрудник) → `gh pr ready 70` → мониторить CI → merge по указанию владельца → комплект пересобрать с новой версией (правило ревью: новый EXE — новая identity).
2. PR-2 этапа 4: таблица команд в README + гейт полноты по `--commands-json` + точка хешей движка/пакетов для диагностики (хвост #64).
3. Этап 1: 155 текстовых ассертов → behavior-тесты (`_gui_source()` в test_gui, `_app()` в test_latest_base_updater); не переносить на точки под удаление.
4. Решения владельца по правилу Codex (см. отчёт) → применить в `codex-layer/AGENTS.md` пакетом через мост, sync, перезапуск Desktop.
5. Мелкие: `reason` в ассерт `test_system_proxy_lease.py:1349`; ключ `"opencode"` → `"opencode-cli"` в `ClientDetector.cs:29` (RED-тест); `codex-windows-sandbox-setup.exe` для read-only sandbox моста — вопрос Codex.
6. Открытые вопросы владельца прежние: шаги мастера; SOCKS5; sing-box.

## Грабли этой сессии
- Heredoc в Bash-инструменте ломается на кавычках → скрипты через Write + `python файл`, коммиты через `git commit -F файл` (память `git-bash-heredoc-unreliable`).
- Монитор с `gh run view` без `-R owner/repo` вне репозитория — «gh-error» в цикле; всегда указывать `-R`.
- Лимит сессии убил три фоновых агента разом; перезапуск на sonnet/opus прошёл.
- Фоновый pytest в worktree: файлы не трогать до итога (тесты читают исходники с диска).
- В основной копии висел sequencer cherry-pick от 12.08 (снят `git cherry-pick --quit`, дерево было чистым).
- Читать Codex-ответ: его shell в read-only sandbox не работал — выводы про файлы слоя он делал по переданному контексту.

## Промпт для нового чата
Продолжение реворка инсталлятора (DANIIL-LAPTOP). Прочитай `rework-bases/Claude/STATUS.md`, верх журнала и этот отчёт (cascade по `##`). Проверь ответ canary в «Ответ с рабочего ПК» (файл новее 2026-09-03 12:27 с другой станции); если canary прошёл — снять draft с PR #70, мониторить CI и сливать по указанию владельца; затем PR-2 (README-таблица + гейт полноты + хеши) в новом worktree от main. Не переключать ветку под фоновым pytest; для локальных сборок `K7_OFFICECLI_BINARY_PATH=$HOME/repos/.officecli-cache/officecli.exe`; итог прогона читать по строке pytest.

## Команда проверки поверхности (проверена)
```powershell
pwsh -NoProfile -File tools\build-gui.ps1 -OutputRoot <out> -Edition Employee -ProductRole Installer            # релиз: 10 команд
pwsh -NoProfile -File tools\build-gui.ps1 -OutputRoot <out> -Edition Employee -ProductRole Installer -TestHooks # тестовый хост: 52
<out>\LLMFoundationInstaller.exe --commands-json
```
