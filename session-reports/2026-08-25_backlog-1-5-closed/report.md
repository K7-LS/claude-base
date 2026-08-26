# Сессия 2026-08-25 · DANIILPC · Закрытие бэклога №1–№5

Продолжение «Claude-канал: разблокировка» (2026-08-21). Все пять вопросов
хендоффа закрыты до конца: код + тесты + PR + CI + merge + релизы + живая
установка.

## TL;DR

- Foundation: `0.5.8` → `0.5.9` → `0.5.10` (installer PR #24, #25, #26).
- claude-base: PR #19–#25, релизы `0.1.17` … `0.1.22`; на DANIILPC — `0.1.22`.
- opencode-base: PR #15, первый канонический K7-LS релиз `opencode-v0.1.14`.
- Найдены и закрыты ПЯТЬ скрытых дефектов session-канала — канал впервые
  работает на реальном consumer.
- Ветка `codex/project-memory-unified` закрыта: ценное перенесено, тег
  `archive/project-memory-unified`, ветка удалена.

## №1 — install не обновлял session-tools state (PRESERVE)

Корень шире отчёта: 0.1.16 поглотил 33 из 34 session-скиллов в managed
surface, а PRESERVE сохранял state, описывающий уже заменённые каталоги.
Фикс (движок `0.5.8`): PRESERVE — только для state той же или новой версии,
с выбросом поглощённых записей; более старый state получает REFRESH —
payload из пакета (ADOPT/REINSTALL/INSTALL, fail-closed на дрейф), state
пересобирается из `session_tools_baseline`. Живое подтверждение — на обоих
таргетах (claude 0.1.8→0.1.17, opencode 0.1.6→0.1.14). Костыль ручной
пересборки state снят.

## №2 — multi-tool session tools

- Политика `tool_count` (открытый вопрос хендоффа): заявленное значение
  обязано точно совпадать с верифицированным содержимым архива, 1..64;
  0, выход за предел, несовпадение — блок до мутации.
- Builder: автообнаружение всех 39 скиллов (155 файлов), в managed surface
  остался только `sync-base`. Updater: транзакция на инструмент, state
  schema 2 с докаткой прерванного снапшота.
- Движок `0.5.9`: капы 32→64 tools / 256→512 файлов, приём schema 2.
- Движок `0.5.10`: портируемые типы файлов в baseline пакета (вылезло на
  живом прогоне: `.py/.lsp` хелперы валили пакет).
- Гейты канарейки/evidence переведены на новый состав
  `{agents:16, skills:0, control_skills:1, session_tools:39}` (PR #20).

## Пять скрытых дефектов канала (все закрыты, все с RED-тестами)

1. PRESERVE-стейл (№1, движок 0.5.8).
2. `claude-candidate-v0.1.0-r2` в списке релизов валил весь список —
   строгий шаблон тега проверялся до фильтра draft/prerelease (0.1.18).
   Канал не работал на consumer НИКОГДА.
3. `gh release verify-asset` звался с именем файла вместо пути — падение из
   любого cwd (0.1.20); fake-gh тестов теперь требует существующий файл.
4. Портируемые типы в baseline (движок 0.5.10).
5. Fingerprint updater'а хешировал `__pycache__/*.pyc`, которые движок
   игнорирует — первый импорт python-хелпера ломал канал (0.1.22);
   живая проверка: pycache на диске → `NO_UPDATE`.

## №3 — OpenCode canonical release

`opencode-v0.1.14` из K7-LS (у до-миграционных релизов attestation мёртв
навсегда). Provider marker переведён на контракт Claude: опционален,
`NOT_REQUIRED` + limitation (PR #15). Канарейка с точным клиентом 1.18.13.
Установлен на DANIILPC: doctor `CANONICAL`, state REFRESH 0.1.6→0.1.14.

## №4 — project-memory и судьба ветки

Единое ядро перенесено на main (PR #22): `core_layout.py` (детект
`Claude/`/`Codex/`, переиспользование, `CORE_CONFLICT` fail-closed),
bootstrap с дефолтом `Claude/`, `gen_project_agents.py`. Hooks ветки
осознанно НЕ перенесены (отсутствие закреплено контрактом). Живое ядро
«Заведомо проигранный бой» распознаётся. Ветка закрыта: тег
`archive/project-memory-unified` (82fd33d), ветка удалена из origin.

## №5 — пин клиента

Новая приёмка фактического 2.1.114 (SHA с бинаря, Authenticode Valid,
живой смоук); пин обновлён в client-acceptance, release-contract,
client-binding, канарейке (PR #24). Канарейка `0.1.21` впервые:
`client_pin.matched: true`. Вердикты POLICY_AUDIT / CLAUDE_PROVIDER_MARKER
уже соответствовали решениям владельца.

## Новое ограничение (в бэклог владельцу)

На DANIILPC ПРИМЕНЕНИЕ session-канала не укладывается в 22-секундный
сетевой бюджет фазового контракта: `gh attestation verify` через прокси —
стабильно ~18 с/вызов (кэш не помогает), а их в цикле три. Проверка списка
укладывается (`NO_UPDATE` работает); доставка обновлений идёт полным
install. Расширение бюджета fallback-пути меняет фазовый контракт журнала —
требует решения владельца. Также вне списка: переработка Installer /
Launch Center (заявлена владельцем 2026-08-21).

## Точные артефакты

- Foundation: `foundation-engine-v0.5.8|0.5.9|0.5.10` — immutable, verify /
  verify-asset / attestation PASS по каждому ассету.
- claude-base: `claude-v0.1.17|0.1.18|0.1.19|0.1.20|0.1.21|0.1.22` — все
  FULL_RELEASE_CLAUDE PASS, RELEASE_INTEGRITY PASS.
- opencode-base: `opencode-v0.1.14` — FULL_RELEASE_OPENCODE PASS,
  RELEASE_INTEGRITY PASS.
- DANIILPC: claude `0.1.22` + движок `0.5.10` (doctor CANONICAL, 39 session
  tools, updater `NO_UPDATE same-tag` при живом pycache); opencode `0.1.14`
  (doctor CANONICAL).
- Полные suite на merge: claude-base 156 passed / 1 skipped; opencode-base
  98 passed / 1 skipped; installer foundation-тесты 178 passed (2 известных
  флейка под нагрузкой, изолированно passed).


## Дополнение (handoff 2026-08-25 08:30 MSK)

Решения владельца в сессии и их исполнение:

- **Тайминг канала (вариант A)**: `-ExtendedNetworkBudget` (только с
  `-HookFallback`) — сетевая фаза 300 с, мутационные тики 22/25/30
  перевыдаются после сети; hook-путь строгий (сторожевой тест). PR #26
  claude-base, релиз `claude-v0.1.23` verified + установлен, живой прогон:
  сетевая фаза канала проходит на прокси (`NO_UPDATE verified-snapshot`),
  затем same-tag установленным updater'ом.
- **Installer/Launch Center**: обследование готово —
  `installer-lc-survey-plan.md` рядом с этим файлом (свод Explore-агента:
  архитектура, болезни, R7-правки, тестовый охват). Владелец согласовал
  фазы Ф0–Ф5, работа начата.

Статус Ф0 на момент handoff:

- R7-правки закоммичены в `fix/r7-single-exe-launch-center` (17d08b9),
  ребейз на main 9e0e43b выполнен, 5 конфликтов разрешено вручную
  (карточка CLAUDE из main сохранена; probe = main `RunCurlProbe` +
  R7-семантика 100–599 + заголовки UA/Accept; дубликат `RunRouteProbe`
  удалён; фейк sing-box требует UA `K7-AI-Launch-Center`).
- Ветка запушена, открыт PR
  https://github.com/K7-LS/llm-foundation-installer/pull/27 — CI арбитр.
- Локальный прогон `tests/test_launcher_runtime.py tests/test_launch_center.py`
  доехал: **7 failed / 32 passed** — реальные расхождения main-тестов с
  R7-правками после ребейза; их починка = достройка Ф0 Известные 4 из 7:
  `test_singbox_route_probe_forwards_real_local_http_request[LaunchCenter-SingBoxHttp|Https]`
  (вероятно, мой UA/Accept в RunCurlProbe против фейка либо probe-семантика),
  `test_singbox_route_launches_exact_client_with_local_proxy_only`,
  `test_complete_target_catalog_matches_real_launch_center_cards`
  (main-каталог целей против R7-карточек XAML). Остальные — перепрогнать
  и снять список. CI PR #27
  покажет то же самое.

Дальше по фазам (план в installer-lc-survey-plan.md):

- Ф0: дождаться CI PR #27 → merge (чинить по CI при падениях; вероятные
  точки — мои разрешения конфликтов в test_launcher_runtime.py и
  UA/Accept в RunCurlProbe против старых main-тестов).
- Ф1: удалить мёртвый `src/gui/InstallerView.xaml` + его 3 ложных теста в
  test_gui.py (строки ~5051, 5078, 5256); вынести хардкоды
  (`scuf-meta.ru:10894` в InstallerApp.cs:2795, путь Chrome :2793,
  probe-URL :2990, версия sing-box в 3 местах) в конфиг/lock с валидацией
  ApprovedHosts; R7-тесты, закрепившие хардкоды, переиграть на конфиг.
- Ф2: разрезка InstallerApp.cs (4697 строк, 26 типов) на модули;
  build-gui.ps1 умеет многофайловость.
- Ф3: SDK-style .csproj (net48 WPF) вместо 1984 строк PowerShell.
- Ф4: сверить хотфиксы Work PC (#19 уже в main — проверить полноту против
  ветки fix/work-pc-upgrade-proxy-recovery).
- Ф5: view-model слой без WPF-зависимости, smoke-тесты привязок.

Рабочие места: ~/repos/llm-foundation-installer (ветка
fix/r7-single-exe-launch-center); релизные worktrees claude-base —
~/repos/.worktrees/claude-multi-tool; движок 0.5.10 распакован в
~/repos/.worktrees/foundation-release-0.5.10/engine.

Ловушка сессии (повторялась трижды): heredoc/JSON-экранирование съедает
backslash при вставке C#/regex-текста через bash-heredoc python-скрипты —
для таких правок использовать Write отдельного .py файла или Edit-tool.

## Дополнение (продолжение Ф0, 2026-08-25 ~09:00 MSK, DANIILPC)

Все падения Ф0 разобраны до корней и починены (коммит fcbac91 в
fix/r7-single-exe-launch-center, запушен, CI PR #27 наблюдается):

1. **12 ERRORs test_system_proxy_lease + 6 FAILED test_launcher_runtime** —
   один корень: в шаблоне фейкового sing-box (test_launcher_runtime.py,
   `_compile_fake_singbox`) два блока 403-ответов содержали реальные переводы
   строк вместо `\r\n` (та самая heredoc-ловушка). Исправлено Edit-tool,
   компиляция фейка проверена изолированно.
2. **test_gui::test_every_installer_has_large_labeled_component_checkboxes** —
   main-тест требовал `Content="Установить"`/`MinWidth="100"`, R7 осознанно
   сделал «Установить комплект»/142 для Codex/OpenCode. Тест допускает оба.
3. **probe-тест, Https-параметры** — R7-добавленные сценарии (user-agent,
   non-success-status) хардкодили маршрут "SingBoxHttp" при сохранённом
   HTTPS-профиле → SESSION_START_FAILED. Заменено на параметр `route`.

Верификация локально: 6 singbox + 12 lease + gui + 4 probe = зелёные.
`test_complete_target_catalog…` из handoff-списка локально прошёл (был флаки).

Локальные падения, которые НЕ код (в CI зелёные, не чинить):
- 10 ERRORs `test_vscode_*` + `test_product_role_exposes…` +
  `test_direct_vpn…[VPN]` — сборка без локальных lock качает клиентов
  (`build-engine.ps1:118`), прокси владельца рвёт загрузку. CI — арбитр.
- `test_direct_vpn…[Direct]` — гонка main-кода: ClientLauncher для
  desktop-целей ждёт выхода клиента 1000 мс (ClientLauncher.cs ~162), под
  нагрузкой/антивирусом пробник не успевает → PASS/-1/CLIENT_RUNNING.
  R7 этот файл не трогал; заведён task-chip на отдельную починку.

## Дополнение (Ф0 закрыта, Ф1 в PR, 2026-08-25 ~11:40 MSK)

- **Ф0 завершена**: CI PR #27 зелёный, смержен squash'ем в main (a60d42e),
  ветка удалена. Владелец дал команду вести конвейер до конца: Ф1→Ф2→Ф3→Ф4→Ф5,
  каждая фаза код+тест+PR+CI+merge, коммит после зелёного локального прогона.
- **Ф1 готова, PR #28 открыт** (ветка feat/f1-dead-view-and-config-extraction,
  9a65891): мёртвый InstallerView.xaml удалён (+guard), его 3 ложных теста
  переиграны на живые виды; policy-текст «VPN/Proxy — это только транспорт…»
  существовал только в мёртвом файле — перенесён в оба живых installer-вида.
  Хардкоды (Chrome-путь, прокси scuf-meta, probe-URL, версия sing-box)
  вынесены в src/gui/product-config.json: встраивается как ресурс
  ProductConfig.json (ProductConfig.cs, схема-валидация как EditionProfile),
  сборка валидирует probe-host против ApprovedHosts и версию против
  runtime-lock; -ProductConfigPath для негативного теста. Литералы '1.13.14'
  из RuntimeBootstrap.cs/build-gui.ps1 удалены.
- Новые известные средовые падения этой машины (не код): 3 authenticode-теста
  использовали pwsh как подписанную фикстуру — Store-alias нечитаем (OSError
  22); в Ф1 добавлен skip. Плюс нагрузочные 90с-таймауты сборки при длинных
  прогонах (проходят поодиночке).
- Ф2 разведана: InstallerApp.cs 5483 строки / 24 top-level типа, карта
  разрезки по границам типов; главный риск — массовые source-assert тесты,
  читающие «InstallerApp.cs» по имени файла (переиграть на glob src/gui).

## Финал (2026-08-25 ~15:35 MSK): все фазы Ф0–Ф5 выполнены и смержены

Конвейер доведён до конца за одну сессию: Ф0 #27 (a60d42e), Ф1 #28
(a4898fe), Ф2 #29 (5c56dab), Ф3 #30 (257d919), Ф4 — сверка без кода
(хотфиксы Work PC уже в main через #19), Ф5 #31 (667c5c0), плюс гонка
ClientLauncher #32 (18516b8). Ветка fix/work-pc-upgrade-proxy-recovery
заархивирована тегом archive/work-pc-upgrade-proxy-recovery и удалена по
решению владельца. Полный сьют: 220 зелёных; средовые исключения DANIILPC
документированы (Store-pwsh скипы; пин OfficeCli — в памяти
installer-builds-officecli-pin). Итоговый отчёт:
`../2026-08-25_installer-lc-phases/report.md`. STATUS.md и ЖУРНАЛ СЕССИЙ
проектного ядра «Заведомо проигранный бой (или нет)» обновлены.
