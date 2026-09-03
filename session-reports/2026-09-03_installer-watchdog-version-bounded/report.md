# Handoff: инсталлятор — гонка watchdog, версия 0.4.1, post-install, BoundedProcess (2026-09-03, DANIIL-LAPTOP)

## TL;DR
- Пять PR по списку сессии, все с тестами RED→GREEN: #65 (watchdog, 4 коммита), #67 (версия 0.4.1), #66 (post-install через резолвер), #68 (BoundedProcess + ClientBootstrap), #69 (остаток трёх модулей, стек на #68).
- Корень флейка watchdog — не «готовность» (гипотеза прошлой сессии), а `File.Replace`: Win32 ReplaceFile делает два переименования, имя файла исчезает (замер 5 906/113 685 опросов; MoveFileEx — 0/69 840). Второй слой из CI: антивирус держит свежий файл → переименование падает → аренда откатывалась → retry 3 с.
- Мержи выполнены по указанию владельца (#65, #67, #66, #68, #69 — цепочка update-branch → CI → merge). Main = `26a6f03`. Комплект 0.4.1 собран из main и выложен в папку синка (прежний в `_прежний-2026-09-03-ночь`), диагностика из синка: OK, 7/7, SHA `a0fde9c5698bca53…` совпал.
- Требование владельца (записано в журнал/STATUS/память): Codex должен спрашивать при любом расхождении и решении, влияющем на результат; автопропуск вопроса — не раньше ~1 ч (сейчас «скрытный режим», ранний автопропуск) — задача стороне Codex.
- Классификация 51 CLI-точки (шаг 1 этапа 1+4): `rework-bases/отчёты/2026-09-03-installer-cli-точки-классификация.md`.

## Источник истины (cascade)
- План с секцией «Исполнение 2026-09-03»: `rework-bases/отчёты/2026-09-02-installer-переработка-план.md`.
- Журнал/статус проекта: `rework-bases/Claude/ЖУРНАЛ СЕССИЙ.md`, `STATUS.md` (верхняя запись 2026-09-03 день).
- Репозиторий `~/repos/llm-foundation-installer`, main = 195188a (#61) на старте; worktrees сессии: `.worktrees/{watchdog-race, version-0.4.1, post-install-resolver, bounded-process, bounded-process-rest}` — убрать после мержей (`git worktree remove`).

## Состояние PR
| PR | Ветка | Что | CI на закрытии |
|---|---|---|---|
| #65 | fix/system-proxy-watchdog-race | подтверждение отсутствия файла 1 с; MoveFileEx; ready-маркер (`system-proxy-watchdog.ready`, PID) → ACQUIRED только после него, иначе `SYSTEM_PROXY_WATCHDOG_START_FAILED`; retry переименования 3 с | зелёный (первый прогон падал: job 5.1 на моём тесте B → четвёртый коммит; job PS7 на чужом флейке диагностики) |
| #67 | chore/version-0.4.1 | APP_VERSION 0.4.1; литералы из build-gui/CI убраны; тесты выводят ожидание из APP_VERSION; FileVersion EXE вместо ассерта на исходник | зелёный; локально 163 passed / 3 skipped |
| #66 | fix/post-install-launch-via-resolver | codex→codex-desktop (appx по activation_id), claude→claude-code, opencode→opencode-cli через cmd.exe из System32 `/k`; отказы — одним предупреждением | зелёный, CLEAN |
| #68 | refactor/bounded-process-clientbootstrap | `src/gui/BoundedProcess.cs` + 7 мест; csproj Compile дополнен; тест на висящий клиент (60 с ping → план завершается за таймаут детектора) | шёл (локально гейт+сборка зелёные; широкий прогон — см. лог `bounded_modules.log` в scratchpad, если сессия ещё жива) |
| #69 | refactor/bounded-process-rest (base = ветка #68) | BaseReleaseUpdater 310 с, ClientDetector 5 с, SingBoxSession 20 с; EmbeddedJson/ProductCatalog/SingBoxConfig — ресурсы, не процессы | шёл |

## Открытые вопросы владельцу (не отвечены, из прошлой сессии)
1. Шаги мастера — реальные экраны или один экран. 2. SOCKS5 оставить. 3. Sing-box для нескольких клиентов (рекомендация Codex: честное ограничение одного клиента).

## Что дальше (по порядку)
1. Сделано: мержи, комплект 0.4.1 в синке, диагностика OK. Осталось: upgrade-canary на одной станции (владелец/сотрудник: `ДИАГНОСТИКА.cmd` → установка → `ДИАГНОСТИКА.cmd`, отчёты в «Ответ с рабочего ПК»).
0. Сторона Codex: разобрать «скрытный режим» вопросов и таймаут автопропуска (цель ≥ 60 мин), правило «спрашивать при расхождении» — в железные правила слоя.
2. Второй флейк модуля (`reacquire_code 20`) — гипотеза: окно между `RestoreState` и `ReleaseMutex` у владельца; тест ждёт реестр, а не освобождение мьютекса. Отдельная задача.
3. Проверить реальные клиенты (`claude.cmd` → node) при пустом PATH в детекторе версии.
4. Этап 1+4: test host для 42 test-only/дизайн-док точек (см. классификацию), таблица команд для 9 продуктовых/инструментальных, гейт полноты; slить FoundationWorkflow-раннер с BoundedProcess (гейт `test_foundation_process_timeout_is_real` завязан на текст).
5. Comment в #68/#69 с итогом локального широкого прогона (если не успел).

## Грабли этой сессии
- Heredoc → Python → файл: `\n` превращается в реальный перевод строки; C# с `\n`/`\"` писать через Write, Python-патчи — через `chr(92)`.
- PowerShell передаёт `$null` в string-параметр .NET как `""` (нужен `[NullString]::Value`); ctypes `GetFileAttributesW` без `restype=c_uint32` даёт -1.
- Внук процесса наследует пайпы EXE: `communicate(timeout)` висит после выхода EXE — вывод в файлы + `wait`.
- Внутри детектора версии PATH пуст — `ping` без полного пути = 9009.
- Классификатор auto-режима блокирует `gh pr merge` (и один раз — просмотр диффа в той же реплике).

## Промпт для нового чата
Продолжение реворка инсталлятора (DANIIL-LAPTOP). Прочитай `rework-bases/Claude/STATUS.md` и верх журнала, затем этот отчёт (cascade по `##`). Открытые PR #65–#69 — проверить, что смержены; если нет — мониторить по последнему run ветки и сливать по порядку (если `gh pr merge` снова заблокирован — сказать владельцу). Затем комплект 0.4.1 в синк + диагностика, и этап 1+4 по классификации CLI-точек. Не переключать ветку под фоновым pytest; параллельные PR — через git worktree; итог прогона читать по строке pytest.

## Команда сборки комплекта (проверена 2026-09-03)
```powershell
pwsh -NoProfile -File tools\build-edition.ps1 -OutputRoot <out> -Edition Employee -DistributionMode Preview -PackageRoot $HOME\K7-packages -ClientSourcesLock .\client-sources.lock.json -RuntimeSourcesLock .\runtime-sources.lock.json -RuntimeArchive .\.work\runtime-cache\sing-box-1.13.14-windows-amd64.zip
```
Выход: EXE, `.cmd` центра запуска, `bundle-manifest.json`, архив sing-box. В папку синка докладываются `tools/worksite-diagnostics.ps1` (из main), `ДИАГНОСТИКА.cmd` (рукописный, из прежней папки) и `КАК-ЗАПУСТИТЬ.md`. Проверка: `pwsh -File worksite-diagnostics.ps1 -BundleRoot <папка синка>` → отчёт в «Ответ с рабочего ПК».
