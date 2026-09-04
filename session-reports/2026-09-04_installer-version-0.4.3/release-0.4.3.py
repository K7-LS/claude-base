# -*- coding: utf-8 -*-
"""Комплект 0.4.3 Employee/Preview: сборка из main с проверками (phase build),
перенос в папку синка с архивом прежнего 0.4.2 и диагностика (phase sync)."""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HOME = Path.home()
REPO = HOME / "repos" / "llm-foundation-installer"
VERSION = "0.4.3"
OUT = REPO / ".work" / "release" / f"employee-{VERSION}"
SYNC = Path(
    r"C:\Users\Даниил\Yandex.Disk\Компьютер DANIILPC\К-7\Отдел автоматизации"
    r"\LLM\Разработка\K7-Launcher-Employee"
)
PREV = SYNC / "_прежний-2026-09-03-вечер"
SCRATCH = Path(__file__).resolve().parent
EXE = "K7-AI-Foundation-Employee-Preview.exe"
CMD = "K7-AI-Launch-Center-Employee-Preview.cmd"
MANIFEST = "bundle-manifest.json"
SINGBOX = "sing-box-1.13.14-windows-amd64.zip"
DIAG_PS1 = "worksite-diagnostics.ps1"
DIAG_CMD = "ДИАГНОСТИКА.cmd"
HOWTO = "КАК-ЗАПУСТИТЬ.md"
PWSH = "pwsh"


def run(args, cwd=None, env=None, check=True):
    r = subprocess.run(
        args, cwd=cwd, env=env, text=True, capture_output=True,
        encoding="utf-8", errors="replace",
    )
    if check and r.returncode != 0:
        print(r.stdout[-3000:])
        print(r.stderr[-3000:])
        raise SystemExit(f"FAIL: {' '.join(map(str, args))} -> {r.returncode}")
    return r


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def phase_build():
    st = run(["git", "status", "--short"], cwd=REPO).stdout.strip()
    if st:
        raise SystemExit(f"FAIL: main copy not clean:\n{st}")
    print(run(["git", "pull", "--ff-only", "origin", "main"], cwd=REPO).stdout.strip()[-400:])
    head = run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO).stdout.strip()
    log = run(["git", "log", "--oneline", "-6"], cwd=REPO).stdout
    print(log)
    app_version = (REPO / "APP_VERSION").read_text(encoding="utf-8").strip()
    if app_version != VERSION:
        raise SystemExit(f"FAIL: APP_VERSION={app_version}, ожидалось {VERSION}")
    for tag in ("#74", "#75"):
        if tag not in log:
            raise SystemExit(f"FAIL: в последних коммитах main нет {tag}")
    if OUT.exists():
        shutil.rmtree(OUT)
    env = dict(os.environ)
    env["K7_OFFICECLI_BINARY_PATH"] = str(HOME / "repos" / ".officecli-cache" / "officecli.exe")
    r = run(
        [
            PWSH, "-NoProfile", "-File", r"tools\build-edition.ps1",
            "-OutputRoot", str(OUT), "-Edition", "Employee",
            "-DistributionMode", "Preview",
            "-PackageRoot", str(HOME / "K7-packages"),
            "-ClientSourcesLock", r".\client-sources.lock.json",
            "-RuntimeSourcesLock", r".\runtime-sources.lock.json",
            "-RuntimeArchive", r".\.work\runtime-cache\sing-box-1.13.14-windows-amd64.zip",
        ],
        cwd=REPO, env=env,
    )
    print(r.stdout[-1500:])
    # Проверки выхода
    for name in (EXE, CMD, MANIFEST, SINGBOX):
        if not (OUT / name).is_file():
            raise SystemExit(f"FAIL: нет {name} в {OUT}")
    manifest = json.loads((OUT / MANIFEST).read_text(encoding="utf-8"))
    exe_sha = sha256(OUT / EXE)
    fv = run(
        [PWSH, "-NoProfile", "-Command",
         f"(Get-Item -LiteralPath '{OUT / EXE}').VersionInfo.FileVersion"],
    ).stdout.strip()
    checks = {
        "manifest.version": (manifest["version"], VERSION),
        "FileVersion": (fv, VERSION + ".0"),
        "exe sha == manifest": (exe_sha, manifest["products"]["installer"]["sha256"]),
        "cmd sha == manifest": (sha256(OUT / CMD), manifest["launch_center_fallback"]["sha256"]),
        "singbox sha == manifest": (sha256(OUT / SINGBOX), manifest["runtime"]["sha256"]),
    }
    ok = True
    for k, (got, exp) in checks.items():
        flag = "OK " if got == exp else "BAD"
        ok = ok and got == exp
        print(f"{flag} {k}: {got}" + ("" if got == exp else f" != {exp}"))
    codex = run([str(OUT / EXE), "--commands-json"], cwd=OUT, check=False)
    print("commands-json exit", codex.returncode, "len", len(codex.stdout))
    print("main HEAD", head, "EXE sha", exe_sha)
    if not ok:
        raise SystemExit("FAIL: проверки комплекта")
    (SCRATCH / "release-0.4.3-build.json").write_text(
        json.dumps({"head": head, "exe_sha256": exe_sha, "file_version": fv}, indent=2),
        encoding="utf-8",
    )
    print("BUILD OK")


def howto_text(old):
    new = SCRATCH.joinpath("whats-new-0.4.3.md").read_text(encoding="utf-8").strip()
    head_re = re.compile(r"Обновлено 2026-09-03, вечер \(сборка 0\.4\.2.*?\n\n", re.S)
    m = head_re.search(old)
    if not m:
        raise SystemExit("FAIL: не найден заголовочный абзац памятки")
    header = (
        "Обновлено 2026-09-04 (сборка 0.4.3 из main с правками #73–#75). Все\n"
        "файлы должны лежать рядом. Админ-права не нужны: всё ставится в профиль\n"
        "пользователя. Прежние комплекты сохранены в подпапках `_прежний-2026-09-02`\n"
        "(0.4.0, до #57), `_прежний-2026-09-03-ночь` (0.4.0, #57–#64),\n"
        "`_прежний-2026-09-03-день` (0.4.1, #65–#69) и `_прежний-2026-09-03-вечер`\n"
        "(0.4.2, #70–#72).\n\n"
    )
    text = old[: m.start()] + header + old[m.end():]
    text = text.replace(
        "Версия продукта в этой сборке — **0.4.2**",
        "Версия продукта в этой сборке — **0.4.3**",
    )
    marker = "## Что нового в 0.4.2"
    if marker not in text:
        raise SystemExit("FAIL: не найден раздел 0.4.2 в памятке")
    text = text.replace(marker, new + "\n\n" + marker, 1)
    return text


def phase_sync():
    build = json.loads((SCRATCH / "release-0.4.3-build.json").read_text(encoding="utf-8"))
    if PREV.exists():
        raise SystemExit(f"FAIL: {PREV} уже есть")
    for name in (EXE, CMD, MANIFEST, SINGBOX, DIAG_PS1, DIAG_CMD, HOWTO):
        if not (SYNC / name).is_file():
            raise SystemExit(f"FAIL: в синке нет {name}")
    old_manifest = json.loads((SYNC / MANIFEST).read_text(encoding="utf-8"))
    if old_manifest["version"] != "0.4.2":
        raise SystemExit(f"FAIL: в синке версия {old_manifest['version']}, ожидалась 0.4.2")
    old_howto = (SYNC / HOWTO).read_text(encoding="utf-8")
    new_howto = howto_text(old_howto)
    PREV.mkdir()
    for name in (EXE, CMD, MANIFEST, SINGBOX, DIAG_PS1, DIAG_CMD, HOWTO):
        shutil.move(str(SYNC / name), str(PREV / name))
    for name in (EXE, CMD, MANIFEST, SINGBOX):
        shutil.copy2(OUT / name, SYNC / name)
    shutil.copy2(REPO / "tools" / DIAG_PS1, SYNC / DIAG_PS1)
    shutil.copy2(PREV / DIAG_CMD, SYNC / DIAG_CMD)
    (SYNC / HOWTO).write_text(new_howto, encoding="utf-8")
    if sha256(SYNC / EXE) != build["exe_sha256"]:
        raise SystemExit("FAIL: SHA EXE в синке не совпал со сборкой")
    print("SYNC OK; prev ->", PREV.name)
    answers = SYNC / "Ответ с рабочего ПК"
    before = {p.name for p in answers.glob("диагностика-*.json")}
    r = run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(SYNC / DIAG_PS1), "-BundleRoot", str(SYNC)],
        check=False,
    )
    print("diag exit", r.returncode)
    print(r.stdout[-1200:])
    if r.stderr.strip():
        print("STDERR:", r.stderr[-800:])
    new = sorted({p.name for p in answers.glob("диагностика-*.json")} - before)
    if not new:
        raise SystemExit("FAIL: отчёт диагностики не появился")
    rep = json.loads((answers / new[-1]).read_text(encoding="utf-8-sig"))
    b = rep.get("bundle", {})
    print("report", new[-1], "status", rep.get("status"), "errors", rep.get("errors"))
    print("bundle.manifest_version", b.get("manifest_version"), "exe_matches_manifest",
          b.get("exe_matches_manifest"), "exe_sha256", b.get("exe_sha256"))
    print("install_plans:", json.dumps(rep.get("install_plans"), ensure_ascii=False)[:1500])
    print("launch_targets:", json.dumps(rep.get("launch_targets"), ensure_ascii=False)[:600])
    if rep.get("status") != "OK" or b.get("manifest_version") != VERSION or b.get("exe_sha256") != build["exe_sha256"]:
        raise SystemExit("FAIL: диагностика не подтвердила комплект")
    print("DIAG OK")


if __name__ == "__main__":
    phase = sys.argv[1] if len(sys.argv) > 1 else ""
    if phase == "build":
        phase_build()
    elif phase == "sync":
        phase_sync()
    else:
        raise SystemExit("usage: release-0.4.3.py build|sync")
