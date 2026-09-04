# -*- coding: utf-8 -*-
"""Выкладка комплекта Employee/Preview в синк: сборка из main с проверками
(phase build), перенос прежнего комплекта в архивную подпапку и диагностика
(phase sync). Параметры: --version 0.4.4 --prev-version 0.4.3
--prev-name _прежний-2026-09-04-утро [--whats-new whats-new-0.4.4.md].
С 0.4.4 комплект несёт файлы установщика Codex (bundled_assets):
сборка идёт с -ClientAssetRoot, файлы копируются и сверяются по SHA."""
import argparse
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
SYNC = Path(
    r"C:\Users\Даниил\Yandex.Disk\Компьютер DANIILPC\К-7\Отдел автоматизации"
    r"\LLM\Разработка\K7-Launcher-Employee"
)
HERE = Path(__file__).resolve().parent
EXE = "K7-AI-Foundation-Employee-Preview.exe"
CMD = "K7-AI-Launch-Center-Employee-Preview.cmd"
MANIFEST = "bundle-manifest.json"
SINGBOX = "sing-box-1.13.14-windows-amd64.zip"
DIAG_PS1 = "worksite-diagnostics.ps1"
DIAG_CMD = "ДИАГНОСТИКА.cmd"
HOWTO = "КАК-ЗАПУСТИТЬ.md"
PWSH = "pwsh"
CLIENT_ASSET_ROOT = REPO / ".work" / "client-assets"


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


def bundled_files(manifest):
    files = []
    for records in (manifest.get("client_assets") or {}).values():
        for record in records:
            files.append((record["file"], record["sha256"], int(record["bytes"])))
    return files


def phase_build(version, expect_prs):
    out = REPO / ".work" / "release" / f"employee-{version}"
    st = run(["git", "status", "--short"], cwd=REPO).stdout.strip()
    if st:
        raise SystemExit(f"FAIL: main copy not clean:\n{st}")
    print(run(["git", "pull", "--ff-only", "origin", "main"], cwd=REPO).stdout.strip()[-400:])
    head = run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO).stdout.strip()
    log = run(["git", "log", "--oneline", "-8"], cwd=REPO).stdout
    print(log)
    app_version = (REPO / "APP_VERSION").read_text(encoding="utf-8").strip()
    if app_version != version:
        raise SystemExit(f"FAIL: APP_VERSION={app_version}, ожидалось {version}")
    for tag in expect_prs:
        if tag not in log:
            raise SystemExit(f"FAIL: в последних коммитах main нет {tag}")
    if out.exists():
        shutil.rmtree(out)
    env = dict(os.environ)
    env["K7_OFFICECLI_BINARY_PATH"] = str(HOME / "repos" / ".officecli-cache" / "officecli.exe")
    r = run(
        [
            PWSH, "-NoProfile", "-File", r"tools\build-edition.ps1",
            "-OutputRoot", str(out), "-Edition", "Employee",
            "-DistributionMode", "Preview",
            "-PackageRoot", str(HOME / "K7-packages"),
            "-ClientSourcesLock", r".\client-sources.lock.json",
            "-RuntimeSourcesLock", r".\runtime-sources.lock.json",
            "-RuntimeArchive", r".\.work\runtime-cache\sing-box-1.13.14-windows-amd64.zip",
            "-ClientAssetRoot", str(CLIENT_ASSET_ROOT),
        ],
        cwd=REPO, env=env,
    )
    print(r.stdout[-1500:])
    # build-edition до фикса печатает пустые предупреждения для клиентов без
    # bundled_assets (@($null) в PowerShell); опасны только именованные —
    # с именем файла после двоеточия.
    named = [
        line for line in (r.stdout + r.stderr).splitlines()
        if "Bundled asset not found" in line
        and re.search(r"it: \S+\.(json|SHA256SUMS|gz)", line)
    ]
    if named:
        raise SystemExit(
            "FAIL: не все файлы комплекта найдены в кеше client-assets:\n"
            + "\n".join(named)
        )
    for name in (EXE, CMD, MANIFEST, SINGBOX):
        if not (out / name).is_file():
            raise SystemExit(f"FAIL: нет {name} в {out}")
    manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    exe_sha = sha256(out / EXE)
    fv = run(
        [PWSH, "-NoProfile", "-Command",
         f"(Get-Item -LiteralPath '{out / EXE}').VersionInfo.FileVersion"],
    ).stdout.strip()
    checks = {
        "manifest.version": (manifest["version"], version),
        "FileVersion": (fv, version + ".0"),
        "exe sha == manifest": (exe_sha, manifest["products"]["installer"]["sha256"]),
        "cmd sha == manifest": (sha256(out / CMD), manifest["launch_center_fallback"]["sha256"]),
        "singbox sha == manifest": (sha256(out / SINGBOX), manifest["runtime"]["sha256"]),
    }
    assets = bundled_files(manifest)
    if not assets:
        raise SystemExit("FAIL: манифест без client_assets — комплект собран без файлов Codex")
    for name, digest, size in assets:
        checks[f"asset {name}"] = (
            (sha256(out / name), (out / name).stat().st_size),
            (digest, size),
        )
    ok = True
    for k, (got, exp) in checks.items():
        flag = "OK " if got == exp else "BAD"
        ok = ok and got == exp
        print(f"{flag} {k}: {got}" + ("" if got == exp else f" != {exp}"))
    codex = run([str(out / EXE), "--commands-json"], cwd=out, check=False)
    print("commands-json exit", codex.returncode, "len", len(codex.stdout))
    print("main HEAD", head, "EXE sha", exe_sha)
    if not ok:
        raise SystemExit("FAIL: проверки комплекта")
    (HERE / f"release-{version}-build.json").write_text(
        json.dumps({"head": head, "exe_sha256": exe_sha, "file_version": fv,
                    "assets": [a[0] for a in assets]}, indent=2),
        encoding="utf-8",
    )
    print("BUILD OK")


def howto_text(old, version, prev_version, prev_name, whats_new, header_note):
    head_re = re.compile(r"Обновлено 2026-\d\d-\d\d.*?\n\n", re.S)
    m = head_re.search(old)
    if not m:
        raise SystemExit("FAIL: не найден заголовочный абзац памятки")
    # список подпапок заканчивается точкой после закрывающей скобки «(…)».
    prev_re = re.compile(r"Прежние комплекты сохранены в подпапках (.*?\))\.", re.S)
    pm = prev_re.search(m.group(0))
    prev_list = (pm.group(1).rstrip() + f" и `{prev_name}`\n({prev_version})") if pm else f"`{prev_name}` ({prev_version})"
    header = (
        f"Обновлено {header_note}. Все\n"
        "файлы должны лежать рядом. Админ-права не нужны: всё ставится в профиль\n"
        f"пользователя. Прежние комплекты сохранены в подпапках {prev_list}.\n\n"
    )
    text = old[: m.start()] + header + old[m.end():]
    text = re.sub(
        r"Версия продукта в этой сборке — \*\*[0-9.]+\*\*",
        f"Версия продукта в этой сборке — **{version}**",
        text,
    )
    marker = f"## Что нового в {prev_version}"
    if marker not in text:
        raise SystemExit(f"FAIL: не найден раздел {prev_version} в памятке")
    if whats_new:
        text = text.replace(marker, whats_new.strip() + "\n\n" + marker, 1)
    return text


def phase_sync(version, prev_version, prev_name, whats_new_path, header_note):
    out = REPO / ".work" / "release" / f"employee-{version}"
    build = json.loads((HERE / f"release-{version}-build.json").read_text(encoding="utf-8"))
    prev = SYNC / prev_name
    if prev.exists():
        raise SystemExit(f"FAIL: {prev} уже есть")
    old_manifest = json.loads((SYNC / MANIFEST).read_text(encoding="utf-8"))
    if old_manifest["version"] != prev_version:
        raise SystemExit(f"FAIL: в синке версия {old_manifest['version']}, ожидалась {prev_version}")
    old_files = [EXE, CMD, MANIFEST, SINGBOX, DIAG_PS1, DIAG_CMD, HOWTO] + [
        a[0] for a in bundled_files(old_manifest)
    ]
    for name in old_files:
        if not (SYNC / name).is_file():
            raise SystemExit(f"FAIL: в синке нет {name}")
    whats_new = Path(whats_new_path).read_text(encoding="utf-8") if whats_new_path else ""
    new_howto = howto_text((SYNC / HOWTO).read_text(encoding="utf-8"), version,
                           prev_version, prev_name, whats_new, header_note)
    new_manifest = json.loads((out / MANIFEST).read_text(encoding="utf-8"))
    new_assets = bundled_files(new_manifest)
    prev.mkdir()
    for name in old_files:
        shutil.move(str(SYNC / name), str(prev / name))
    for name in [EXE, CMD, MANIFEST, SINGBOX] + [a[0] for a in new_assets]:
        shutil.copy2(out / name, SYNC / name)
    shutil.copy2(REPO / "tools" / DIAG_PS1, SYNC / DIAG_PS1)
    shutil.copy2(prev / DIAG_CMD, SYNC / DIAG_CMD)
    (SYNC / HOWTO).write_text(new_howto, encoding="utf-8")
    if sha256(SYNC / EXE) != build["exe_sha256"]:
        raise SystemExit("FAIL: SHA EXE в синке не совпал со сборкой")
    for name, digest, size in new_assets:
        if sha256(SYNC / name) != digest or (SYNC / name).stat().st_size != size:
            raise SystemExit(f"FAIL: файл комплекта {name} в синке не совпал с манифестом")
    print("SYNC OK; prev ->", prev.name, "; assets:", [a[0] for a in new_assets])
    answers = SYNC / "Ответ с рабочего ПК"
    before = {p.name for p in answers.glob("диагностика-*.json")}
    r = run(
        [PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(SYNC / DIAG_PS1), "-BundleRoot", str(SYNC)],
        check=False,
    )
    print("diag exit", r.returncode)
    print(r.stdout[-1200:])
    new = sorted({p.name for p in answers.glob("диагностика-*.json")} - before)
    if not new:
        raise SystemExit("FAIL: отчёт диагностики не появился")
    rep = json.loads((answers / new[-1]).read_text(encoding="utf-8-sig"))
    b = rep.get("bundle", {})
    print("report", new[-1], "status", rep.get("status"), "errors", rep.get("errors"))
    print("bundle.manifest_version", b.get("manifest_version"), "exe_matches_manifest",
          b.get("exe_matches_manifest"))
    print("install_plans:", json.dumps(rep.get("install_plans"), ensure_ascii=False)[:1200])
    print("launch_targets:", json.dumps(rep.get("launch_targets"), ensure_ascii=False)[:600])
    if rep.get("status") != "OK" or b.get("manifest_version") != version or b.get("exe_sha256") != build["exe_sha256"]:
        raise SystemExit("FAIL: диагностика не подтвердила комплект")
    print("DIAG OK")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["build", "sync"])
    ap.add_argument("--version", required=True)
    ap.add_argument("--prev-version")
    ap.add_argument("--prev-name")
    ap.add_argument("--whats-new")
    ap.add_argument("--header-note", default="")
    ap.add_argument("--expect-pr", action="append", default=[])
    a = ap.parse_args()
    if a.phase == "build":
        phase_build(a.version, a.expect_pr)
    else:
        if not (a.prev_version and a.prev_name):
            raise SystemExit("sync: нужны --prev-version и --prev-name")
        phase_sync(a.version, a.prev_version, a.prev_name, a.whats_new,
                   a.header_note or f"2026-09-04 (сборка {a.version} из main)")
