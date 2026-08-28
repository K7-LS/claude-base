# Реворк двух баз, этап 2 на DANIILPC: релизы, приёмки Codex, карта понимания

Дата: 2026-08-28. Устройство: DANIILPC (developer-десктоп с релизной
инфраструктурой). Продолжение handoff с ноутбука
(`../2026-08-28_rework-two-bases-stage2/report.md`). Ядро проекта — папка
«Реворк двух баз» (junction `%USERPROFILE%\rework-bases`); журнал и STATUS
там обновлены.

## Арка сессии

1. **Релиз 0.1.24** собран из main хаба (PR #27+#28) полной цепочкой
   `run_offline_acceptance → live_canary → final_evidence → promote_candidate →
   gh release create → release_verifier → create_package_acceptance` — все
   вердикты PASS. Релизные рабочие места этой машины: worktree
   `~/repos/.worktrees/claude-multi-tool`, движок 0.5.10 c evidence в
   `~/repos/.worktrees/foundation-release-0.5.10/`.
2. **Smoke $sync-base поймал дефект PR #28**: движок в install-ветке отдаёт
   `BLOCKED_USER_DECISION` ошибкой `{status,code,message}` БЕЗ
   `unknown_entries` (Throw-Foundation); список несёт только `plan`. На
   ноутбуке тестировался plan-путь — install-путь остался непокрыт; StrictMode
   ронял синк (PropertyNotFoundStrict). Фикс: свойство через
   PSObject.Properties, при отсутствии — поход в `plan` за списком, retry
   install c `-LocalExceptionPath`; RED-тест с фейковым движком обеих форм.
   PR #29 → CI зелёный → merge.
3. **Релиз 0.1.25** тем же конвейером; установлен здесь: доктор
   `CANONICAL_WITH_LOCAL_EXCEPTIONS`, `skills/codex-bridge` сохранён как
   local exception (`~/.llm-foundation/state/claude/local-exceptions.json`).
4. **Приёмка контура Codex'ом** (мост, фоновые курьеры, пакеты ~20 мин):
   health-check 7/7 PASS, контур PASS по всем пунктам, независимый аудит PASS.
5. **Вердикты Codex по drift исполнены**: (а) канон hooks =
   его one-way (`render_hooks_json` рендерит байт-в-байт его файл — без
   перезаписи и сбития доверия хукам); (б) `mcp_servers.cua_repl` — App-owned
   runtime table (canon-newer, вынос за managed-маркер, детерминированный
   дедуп дублей). После sync: `codex_sync.py check` — exit 0, drift ПУСТ.
6. **Шаг 4 «карта понимания»**: дизайн согласован пакетами через мост
   (его вердикты по (а)-(г) + замечания), реализован: схема v1
   (`skills/understanding-map/schemas/…` + копия в корне плагина сборщиком),
   `map_store.py` (plan/apply, CAS, backup, atomic), `render_map.py`
   (canonical→view, `--mode markdown`, блок решений), границы
   FACTS_CONFLICT/DECISIONS в 4 скиллах одним релизом.
7. **Первая приёмка Codex — FAIL (6 расхождений)**, все воспроизводимо
   доказаны его runtime-пробами и закрыты: source_ids null/не-строки →
   управляемый INVALID_DATA; абсолютный Windows-путь по нормализованной
   форме; уникальность id охватывает next_step; markdown через общий
   `canonical_escaped()`; CAS под межпроцессным lock-файлом с ре-проверкой
   ревизии; MAP_CONFLICT несёт diff. Плюс перенос disk-only неизвестных
   полей при update. **Повторная приёмка — PASS 6/6**; у Codex установлены
   project-controls 0.3.1 и construction-documents 0.3.0.
8. **Этап 2а (installer)**: независимая разведка — 27 кандидатов
   оптимизации/объединения с доказательствами и порядком исполнения;
   сохранена в `отчёты/2026-08-28-installer-кандидаты-оптимизации.md`
   проекта. Код НЕ трогали: ждём решения владельца и сверки с §5 отчёта
   о блокерах (остался на ноутбуке).

## Точные артефакты

- Релизы: `claude-v0.1.24`, `claude-v0.1.25` (verified, package-acceptance
  PASS); хаб PR #29 смержен.
- База `~/.claude`: коммиты 52aba63 (вердикты hooks/cua_repl), b7d68f0
  (канон карты v1), d3ddb2d (6 фиксов приёмки) — запушены.
- Тесты: хаб 162 passed / 1 skip; слой скриптов 147 passed
  (в т.ч. test_understanding_map.py — 28).
- Мостовой тред приёмок: `01a047d6-8b9f-72b2-9f30-fc3cd600f21b`.

## Правила, добытые кровью (новые)

- Движок Foundation отдаёт BLOCKED_USER_DECISION в ДВУХ формах: plan — объект
  с unknown_entries, install — ошибка без списка. Контракт-тесты должны крыть
  обе; «проверено на plan» ≠ «работает на install».
- `mcp__codex__codex-reply` теряет тред после рестарта MCP-сервера
  («Session not found» при целом rollout). Фолбэк — CLI
  `codex exec resume <threadId> -c mcp_servers.claude.enabled=false`;
  вписан в скилл codex-bridge. Финал дальше ловится монитором rollout.
- Канон hooks, совпадающий с диском байт-в-байт, — способ закрыть drift БЕЗ
  перезаписи hooks.json (перезапись сбивает доверие хукам Codex).
- PS-переносы: продолжение выражения допустимо после оператора, не перед ним
  (`('a' + \n 'b')`, не `('a' \n + 'b')`); Add-Content в WinPS 5.1 пишет
  ANSI — для логов, читаемых Python'ом, нужен `-Encoding UTF8`.
- Приёмка «свежим взглядом» другой LLM реально ловит то, что пропустили и
  автор, и его тесты (6 из 6 расхождений — по делу; зелёный набор тестов
  дефекты не покрывал). Паттерн «пакет → FAIL со списком → фикс → re-PASS»
  дешевле самопроверки.

## Открытые хвосты

1. Этап 2а: исполнение по списку кандидатов — после решения владельца
   (сверить мой список с §5 с ноутбука; порядок предложен в отчёте).
2. Этап 3 (аудит плагинов мира, поиск prompt-improver) — строго после 2а.
3. Слой соответствия по региону — закрытое решение, не трогать.
