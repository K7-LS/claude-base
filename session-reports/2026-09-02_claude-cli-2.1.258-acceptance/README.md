# Приёмка клиента Claude Code 2.1.258 — 2026-09-02

Вердикт: **PASS** для бинарника. Кандидат акта — `client-acceptance-2.1.258.json`.

Управляемые файлы базы (`~/.claude/base/runtime/client-acceptance.json`,
`~/.claude/base/runtime/release-contract.json`) **не изменялись** — обоснование ниже.

## Что проверено и чем подтверждено

| Проверка | Результат | Как получено |
|---|---|---|
| SHA-256 бинарника | `22f5f3a44093e14c75a4d1c8ce25c730b21dd634318fbe3268e9057d12b17c41` | `sha256sum ~/.local/bin/claude.exe` |
| Размер | 218 507 936 байт | `stat -c%s` |
| Подпись Authenticode | `Valid` | `Get-AuthenticodeSignature` |
| Издатель / УЦ | Anthropic, PBC / DigiCert Trusted G4 Code Signing RSA4096 SHA384 2021 CA1 | там же |
| Метка времени | есть | `TimeStamperCertificate` не пуст |
| Срок сертификата подписанта | до 2026-10-21 | `NotAfter` |
| Смоук `--version` | `2.1.258 (Claude Code)`, код 0 | запуск бинарника |
| Смоук `--help` | код 0 | запуск бинарника |
| Обращений к модели | 0 | обе команды локальные |
| URL релиза | HTTP 200, `Content-Length` = 218 507 936 (совпадает с локальным файлом) | `Invoke-WebRequest -Method Head` |

Не проверено (зафиксировано в `limitations` акта):

- SHA-256 удалённого файла по URL релиза — потребовало бы скачивания ~218 МБ; сверен только размер;
- бинарник получен штатным `claude update`, а не свежей загрузкой по указанному URL;
- provider login, регион, доступность модели, канареечный прогон базы — вне объёма приёмки бинарника.

## Почему управляемые контракты не тронуты

1. **Двойная фиксация по хэшу.** Оба файла закреплены и по пути, и по SHA-256, и по размеру
   сразу в двух местах:
   - `~/.claude/base/components.lock.json` — lock релиза базы;
   - `~/.llm-foundation/state/claude/active.json` — состояние лаунчера.

   На момент приёмки фактические хэши **совпадают** с зафиксированными
   (`ca8ab6f7…` для `client-acceptance.json`, `f7ad152b…` для `release-contract.json`).
   Ручная правка немедленно разводит файл с обоими lock.

2. **Версия клиента зашита в код базы.** `runtime/update-session-tools.ps1`, строка 517:

   ```powershell
   if ($Manifest.client.id -cne 'claude-code' -or $Manifest.client.supported_version -cne '2.1.114') { throw 'client binding differs' }
   ```

   Это константа в скрипте, а не чтение контракта: правка JSON её не меняет.

3. **Манифест релиза приходит с сервера.** `~/.llm-foundation/state/session-tools/claude/downloads/release-manifest.json`
   заявляет `supported_version: 2.1.114`. Именно его проверяет скрипт из п. 2.

4. **`release-contract.json` — не локальный факт, а заявление релиза.** Поле
   `supported_version` там описывает, что заявила база 0.1.25, а не то, что установлено на машине.
   Переписать его локально — значит заставить базу утверждать о поддержке, которой она не объявляла.

Вывод: подъём поддерживаемой версии клиента до 2.1.258 — это **выпуск новой версии базы**
(репозиторий `claude-base-v2`: константа в `update-session-tools.ps1`, манифест релиза, lock),
а не редактирование двух JSON на машине.

## Побочный факт

После обновления CLI фактическая версия (2.1.258) разошлась с принятой в базе (2.1.114).
Расхождение существовало и раньше между слоями: манифест лаунчера
`~/.llm-foundation/clients/claude-code/current.json` держал 2.1.218, а `base/runtime` — 2.1.114.
В `base/STATUS.json` открытый блокер сформулирован для версии 2.1.218:
«the zero-model live base canary for Claude Code 2.1.218 has not run».

## Состояние установок на 2026-09-02

| Слой | Версия |
|---|---|
| `~/.local/bin/claude.exe` | 2.1.258 |
| `~/.llm-foundation/bin/claude.exe` (+ манифест `current.json`) | 2.1.258 |
| Claude Desktop | 1.40609.1 развёрнут, активируется после полного закрытия приложения |
| claude-code внутри десктопа | 2.1.246 (обновляется приложением) |
| Принято в базе (`base/runtime`) | 2.1.114 |
