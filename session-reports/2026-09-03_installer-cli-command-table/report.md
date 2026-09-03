# Handoff: инсталлятор — этап 1+4, PR-1: таблица команд и тестовый хост (2026-09-03, DANIIL-LAPTOP)

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
