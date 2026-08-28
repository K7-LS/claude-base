# -*- coding: utf-8 -*-
"""Живой просмотр журнала переговоров Claude↔Codex как чата.

Запуск:  python ~/.claude/scripts/interop_chat_server.py
Открыть: http://127.0.0.1:7343

Сервер только локальный (127.0.0.1), читает ~/.claude/interop/dialog.md.
Страница опрашивает /raw каждые 2 секунды и дорисовывает новые записи.
"""
import http.server
import json
import socketserver
import urllib.parse
from pathlib import Path

PORT = 7343
JOURNAL = Path.home() / ".claude" / "interop" / "dialog.md"
SESSIONS = Path.home() / ".codex" / "sessions"


def list_sessions(limit: int = 40) -> list:
    items = []
    for f in SESSIONS.glob("*/*/*/rollout-*.jsonl"):
        items.append(f)
    items.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in items[:limit]:
        first_user, tokens = "", None
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    try:
                        p = json.loads(line).get("payload", {})
                    except ValueError:
                        continue
                    t = p.get("type")
                    if t == "user_message" and not first_user:
                        first_user = (p.get("message") or "")[:200]
                    elif t == "token_count":
                        tokens = (p.get("info") or {}).get(
                            "total_token_usage", {}).get("total_tokens", tokens)
        except OSError:
            continue
        out.append({
            "file": str(f.relative_to(SESSIONS)).replace("\\", "/"),
            "name": f.stem.replace("rollout-", ""),
            "mtime": f.stat().st_mtime,
            "size": f.stat().st_size,
            "first_user": first_user,
            "tokens": tokens,
        })
    return out


def parse_session(rel: str) -> list:
    f = (SESSIONS / rel).resolve()
    if SESSIONS.resolve() not in f.parents or f.suffix != ".jsonl" or not f.exists():
        raise FileNotFoundError(rel)
    steps = []

    def clip(s, n):
        s = (s or "").strip()
        return s if len(s) <= n else s[:n] + "\n… [обрезано]"

    with open(f, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                p = json.loads(line).get("payload", {})
            except ValueError:
                continue
            t = p.get("type")
            if t == "user_message":
                steps.append({"kind": "user", "text": clip(p.get("message"), 4000)})
            elif t == "agent_message":
                steps.append({"kind": "codex", "text": clip(p.get("message"), 4000)})
            elif t == "custom_tool_call":
                steps.append({"kind": "tool",
                              "text": (p.get("name") or "tool") + ": " + clip(p.get("input"), 1500)})
            elif t == "custom_tool_call_output":
                out = p.get("output")
                if isinstance(out, list):
                    out = "\n".join(x.get("text", "") for x in out if isinstance(x, dict))
                steps.append({"kind": "out", "text": clip(str(out), 1200)})
            elif t == "task_complete":
                steps.append({"kind": "done", "text": "task_complete"})
    return steps

PAGE = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Мост Claude ⇄ Codex</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><circle cx='9' cy='16' r='6' fill='%23D97757'/><circle cx='23' cy='16' r='6' fill='%23339CFF'/></svg>">
<style>
  :root {
    --bg: #141416;
    --panel: #1d1d21;
    --panel-2: #232328;
    --line: #2c2c31;
    --ink: #e8e6e1;
    --dim: #8b8a85;
    --claude: #d97757;
    --claude-tint: #2a201c;
    --codex: #339cff;
    --codex-tint: #1a2230;
    --mono: "Cascadia Code", "Cascadia Mono", Consolas, monospace;
    --sans: "Segoe UI Variable Text", "Segoe UI", system-ui, sans-serif;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { background: var(--bg); color: var(--ink); font-family: var(--sans); }
  body { min-height: 100vh; }

  header {
    position: sticky; top: 0; z-index: 10;
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 22px;
    background: color-mix(in srgb, var(--bg) 86%, transparent);
    backdrop-filter: blur(10px);
    border-bottom: 1px solid var(--line);
  }
  .wordmark { display: flex; align-items: center; gap: 10px; font-family: var(--mono); font-size: 13px; letter-spacing: .14em; }
  .wordmark .c1 { color: var(--claude); font-weight: 600; }
  .wordmark .c2 { color: var(--codex); font-weight: 600; }
  .wordmark .x  { color: var(--dim); }
  .status { display: flex; align-items: center; gap: 8px; font-family: var(--mono); font-size: 11.5px; color: var(--dim); }
  .tabs { display: flex; gap: 14px; font-family: var(--mono); font-size: 12px; }
  .tabs a { color: var(--dim); text-decoration: none; padding: 3px 2px; border-bottom: 2px solid transparent; }
  .tabs a.on { color: var(--ink); border-bottom-color: var(--codex); }
  .sess-row { position: relative; z-index: 1; display: block; padding: 10px 14px; margin: 8px 0;
    background: var(--panel); border: 1px solid var(--line); border-radius: 10px;
    cursor: pointer; text-decoration: none; color: var(--ink); }
  .sess-row:hover { border-color: color-mix(in srgb, var(--codex) 40%, var(--line)); }
  .sess-row .id { font-family: var(--mono); font-size: 11px; color: var(--dim); }
  .sess-row .fu { font-size: 13px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
  #alt.feed::before { display: none; }
  .step { position: relative; z-index: 1; margin: 10px 0; }
  .step .bubble { max-width: 76%; }
  .step.user .bubble { margin-left: auto; background: var(--claude-tint);
    border-color: color-mix(in srgb, var(--claude) 30%, var(--line)); }
  .step.codex .bubble { margin-right: auto; background: var(--codex-tint);
    border-color: color-mix(in srgb, var(--codex) 30%, var(--line)); }
  .step .tg { width: min(92%, 680px); margin: 0 auto; font-family: var(--mono);
    font-size: 11.5px; background: var(--panel-2); border: 1px solid var(--line);
    border-radius: 8px; padding: 7px 11px; white-space: pre-wrap; overflow-wrap: break-word; color: var(--dim); }
  .step.done .tg { color: #4ade80; text-align: center; }
  .backlink { position: relative; z-index: 1; display: inline-block; margin: 6px 0 14px;
    font-family: var(--mono); font-size: 12px; color: var(--codex); text-decoration: none; }
  .pulse { width: 8px; height: 8px; border-radius: 50%; background: #4ade80; }
  .pulse.live { animation: pulse 2s ease-in-out infinite; }
  .pulse.dead { background: #f87171; animation: none; }
  @keyframes pulse { 0%,100% { box-shadow: 0 0 0 0 rgba(74,222,128,.5);} 50% { box-shadow: 0 0 0 6px rgba(74,222,128,0);} }

  .feed { max-width: 780px; margin: 0 auto; padding: 28px 18px 90px; position: relative; }
  /* линия моста */
  .feed::before {
    content: ""; position: absolute; top: 0; bottom: 0; left: 50%;
    width: 1px; background: linear-gradient(to bottom, transparent, var(--line) 60px, var(--line) calc(100% - 40px), transparent);
  }

  .day { position: relative; text-align: center; margin: 26px 0 18px; }
  .day span {
    position: relative; z-index: 1; background: var(--bg); padding: 3px 14px;
    font-family: var(--mono); font-size: 11px; color: var(--dim); letter-spacing: .12em;
    border: 1px solid var(--line); border-radius: 99px;
  }

  .entry { position: relative; margin: 22px 0; }
  .meta {
    display: flex; align-items: center; gap: 8px;
    font-family: var(--mono); font-size: 11px; color: var(--dim);
    margin-bottom: 8px;
  }
  .entry.from-claude .meta { justify-content: flex-end; }
  .meta .dir-claude { color: var(--claude); }
  .meta .dir-codex  { color: var(--codex); }
  .meta .mdl { font-style: normal; opacity: .72; }
  /* точка на линии моста */
  .entry::after {
    content: ""; position: absolute; top: 3px; left: 50%; transform: translateX(-50%);
    width: 7px; height: 7px; border-radius: 50%; background: var(--dim);
  }
  .entry.from-claude::after { background: var(--claude); }
  .entry.from-codex::after  { background: var(--codex); }
  .entry.fresh::after { animation: ripple 1.2s ease-out 2; }
  @keyframes ripple { 0% { box-shadow: 0 0 0 0 rgba(232,230,225,.35);} 100% { box-shadow: 0 0 0 12px rgba(232,230,225,0);} }

  .bubble {
    position: relative; z-index: 1;
    max-width: 46%; padding: 11px 14px; border-radius: 14px;
    border: 1px solid var(--line); background: var(--panel);
    font-size: 14px; line-height: 1.5;
    white-space: pre-wrap; overflow-wrap: break-word;
  }
  .entry.from-claude .bubble.q { margin-left: auto; background: var(--claude-tint); border-color: color-mix(in srgb, var(--claude) 34%, var(--line)); border-bottom-right-radius: 4px; }
  .entry.from-claude .bubble.a { margin-right: auto; margin-top: 10px; background: var(--codex-tint); border-color: color-mix(in srgb, var(--codex) 30%, var(--line)); border-bottom-left-radius: 4px; }
  .entry.from-codex .bubble.q { margin-right: auto; background: var(--codex-tint); border-color: color-mix(in srgb, var(--codex) 34%, var(--line)); border-bottom-left-radius: 4px; }
  .entry.from-codex .bubble.a { margin-left: auto; margin-top: 10px; background: var(--claude-tint); border-color: color-mix(in srgb, var(--claude) 30%, var(--line)); border-bottom-right-radius: 4px; }
  .speaker { display: block; font-family: var(--mono); font-size: 10.5px; letter-spacing: .1em; margin-bottom: 5px; }
  .speaker.s-claude { color: var(--claude); }
  .speaker.s-codex  { color: var(--codex); }

  /* технические вызовы инструментов — телеграммы на линии */
  .entry.tool .tg {
    position: relative; z-index: 1;
    width: min(88%, 620px); margin: 0 auto;
    background: var(--panel-2); border: 1px solid var(--line); border-radius: 10px;
    font-family: var(--mono); font-size: 12px; line-height: 1.55;
  }
  .tg summary {
    list-style: none; cursor: pointer; padding: 8px 12px;
    display: flex; align-items: center; gap: 9px; color: var(--dim);
  }
  .tg summary::-webkit-details-marker { display: none; }
  .tg .chip {
    padding: 1px 8px; border-radius: 6px; font-size: 11px;
    background: color-mix(in srgb, var(--codex) 16%, transparent); color: var(--codex);
  }
  .tg .gist { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1; min-width: 0; }
  .tg .body { border-top: 1px solid var(--line); padding: 10px 12px; white-space: pre-wrap; overflow-wrap: break-word; color: var(--ink); }
  .tg .body b { color: var(--dim); font-weight: 600; }
  .entry .tg.err { border-color: #7f2d2d; background: #221417; width: min(88%, 620px); margin: 0 auto;
    font-family: var(--mono); font-size: 12px; }
  .entry .tg.err .body { border-top: none; color: #f0a8a8; }

  .empty { text-align: center; color: var(--dim); font-size: 14px; padding: 90px 20px; position: relative; z-index: 1; }
  .empty code { font-family: var(--mono); font-size: 12.5px; color: var(--ink); }

  #newpill {
    position: fixed; left: 50%; bottom: 26px; transform: translateX(-50%);
    padding: 8px 16px; border-radius: 99px; border: 1px solid var(--line);
    background: var(--panel-2); color: var(--ink);
    font-family: var(--mono); font-size: 12px; cursor: pointer;
    display: none; z-index: 20;
  }
  #newpill.show { display: block; }

  @media (max-width: 640px) {
    .bubble { max-width: 78%; }
    .feed::before { left: 12px; }
    .entry::after { left: 12px; }
    .entry .bubble { margin-left: 28px !important; margin-right: 0 !important; }
    .entry.tool .tg { margin-left: 28px; width: auto; }
  }
  @media (prefers-reduced-motion: reduce) {
    .pulse.live, .entry.fresh::after { animation: none; }
  }
  :focus-visible { outline: 2px solid var(--codex); outline-offset: 2px; }
</style>
</head>
<body>
<header>
  <div class="wordmark"><span class="c1">CLAUDE</span><span class="x">⇄</span><span class="c2">CODEX</span><span class="x">· мост</span></div>
  <nav class="tabs"><a href="#" id="tab-feed" class="on">переписка</a><a href="#sessions" id="tab-sess">сессии Codex</a></nav>
  <div class="status"><span id="dot" class="pulse"></span><span id="stat">подключение…</span></div>
</header>
<main class="feed" id="feed"></main>
<main class="feed" id="alt" hidden></main>
<button id="newpill" type="button">новые записи ↓</button>

<script>
"use strict";
const feed = document.getElementById("feed");
const stat = document.getElementById("stat");
const dot = document.getElementById("dot");
const pill = document.getElementById("newpill");
let lastText = null;
let rendered = 0;   // сколько записей уже на странице
let lastDay = "";

function esc(s) {
  return s.replace(/[&<>]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
}
function pretty(s) {
  s = s.trim();
  if (s.startsWith("{") || s.startsWith("[")) {
    try { return JSON.stringify(JSON.parse(s), null, 1); } catch (e) {}
  }
  return s;
}

function parse(text) {
  const entries = [];
  const blocks = text.split(/^## /m).filter(b => b.trim());
  for (const b of blocks) {
    const fail = b.match(/^(\\d{4}-\\d{2}-\\d{2}) (\\d{2}:\\d{2}:\\d{2}) — ⚠ ОШИБКА МОСТА, (Claude → Codex|Codex → Claude) \\((.*?)\\)\\s*\\n([\\s\\S]*)$/);
    if (fail) {
      entries.push({ day: fail[1], time: fail[2], tool: fail[4],
        from: fail[3].startsWith("Claude") ? "claude" : "codex",
        isError: true, q: fail[5].trim(), a: "" });
      continue;
    }
    const m = b.match(/^(\\d{4}-\\d{2}-\\d{2}) (\\d{2}:\\d{2}:\\d{2}) — (Claude → Codex|Codex → Claude) \\((.*?)\\)\\s*\\n([\\s\\S]*)$/);
    if (!m) continue;
    const [, day, time, dir, tool] = m;
    let body = m[5];
    const e = { day, time, tool, from: dir.startsWith("Claude") ? "claude" : "codex" };
    const mPair = body.match(/^модели: (.+?) → (.+?)\\n/);
    const mOne = body.match(/^модель: (.+?)\\n/);
    if (mPair) { e.mInit = mPair[1]; e.mResp = mPair[2]; body = body.slice(mPair[0].length); }
    else if (mOne) { e.mInit = mOne[1]; body = body.slice(mOne[0].length); }
    if (e.from === "claude") {
      const i = body.indexOf("**Codex ответил:**");
      e.q = (i >= 0 ? body.slice(0, i) : body).trim();
      e.a = i >= 0 ? body.slice(i + 18).trim() : "";
    } else {
      const iq = body.indexOf("**Запрос:**");
      const ia = body.indexOf("**Claude вернул:**");
      e.q = (iq >= 0 ? body.slice(iq + 11, ia >= 0 ? ia : undefined) : body).trim();
      e.a = ia >= 0 ? body.slice(ia + 18).trim() : "";
      e.isTool = true;   // вызов инструмента, не свободная переписка
    }
    entries.push(e);
  }
  return entries;
}

function renderEntry(e, fresh) {
  if (e.day !== lastDay) {
    lastDay = e.day;
    const d = document.createElement("div");
    d.className = "day";
    d.innerHTML = "<span>" + esc(e.day) + "</span>";
    feed.appendChild(d);
  }
  const div = document.createElement("article");
  const shortM = m => m === "?" ? "" : m.replace(/^claude-/, "");
  const side = (name, cls, model) =>
    '<span class="' + cls + '">' + name +
    (model && shortM(model) ? '<i class="mdl">·' + esc(shortM(model)) + "</i>" : "") + "</span>";
  const dirLabel = e.from === "claude"
    ? side("CLAUDE", "dir-claude", e.mInit) + " → " + side("CODEX", "dir-codex", e.mResp)
    : side("CODEX", "dir-codex", e.mInit) + " → " + side("CLAUDE", "dir-claude", e.mResp);
  if (e.isError) {
    div.className = "entry tool from-" + e.from + (fresh ? " fresh" : "");
    div.innerHTML =
      '<div class="meta">' + dirLabel + " · " + esc(e.time) + "</div>" +
      '<div class="tg err"><div class="body">⚠ ОШИБКА МОСТА (' + esc(e.tool) + ')\\n' + esc(e.q) + "</div></div>";
  } else if (e.isTool) {
    div.className = "entry tool from-" + e.from + (fresh ? " fresh" : "");
    const gist = e.q.replace(/\\s+/g, " ").slice(0, 90);
    div.innerHTML =
      '<div class="meta">' + dirLabel + " · " + esc(e.time) + "</div>" +
      '<details class="tg"><summary><span class="chip">' + esc(e.tool.replace(/^mcp__claude__/, "")) + "</span>" +
      '<span class="gist">' + esc(gist) + "</span></summary>" +
      '<div class="body"><b>запрос:</b>\\n' + esc(pretty(e.q)) + "\\n\\n<b>ответ:</b>\\n" + esc(pretty(e.a)) + "</div></details>";
  } else {
    div.className = "entry from-" + e.from + (fresh ? " fresh" : "");
    const s1 = e.from === "claude" ? "claude" : "codex";
    const s2 = e.from === "claude" ? "codex" : "claude";
    div.innerHTML =
      '<div class="meta">' + dirLabel + " · " + esc(e.time) + "</div>" +
      '<div class="bubble q"><span class="speaker s-' + s1 + '">' + s1.toUpperCase() + '</span>' + esc(e.q) + "</div>" +
      (e.a ? '<div class="bubble a"><span class="speaker s-' + s2 + '">' + s2.toUpperCase() + '</span>' + esc(e.a) + "</div>" : "");
  }
  feed.appendChild(div);
}

function nearBottom() {
  return window.innerHeight + window.scrollY >= document.body.scrollHeight - 140;
}
pill.addEventListener("click", () => {
  window.scrollTo({ top: document.body.scrollHeight });
  pill.classList.remove("show");
});
window.addEventListener("scroll", () => { if (nearBottom()) pill.classList.remove("show"); });

async function tick() {
  try {
    const r = await fetch("/raw", { cache: "no-store" });
    // журнал пишется на Windows с CRLF, а точка в JS-регэкспах не матчит \\r
    const text = (await r.text()).replace(/\\r\\n/g, "\\n");
    dot.className = "pulse live";
    if (text !== lastText) {
      lastText = text;
      const entries = parse(text);
      if (rendered > entries.length) {   // журнал очистили — перерисовать
        feed.innerHTML = ""; rendered = 0; lastDay = "";
      }
      const wasBottom = nearBottom();
      const fresh = rendered > 0;
      for (let i = rendered; i < entries.length; i++) renderEntry(entries[i], fresh);
      if (entries.length === 0 && rendered === 0) {
        feed.innerHTML = '<div class="empty">Мост молчит. Записи появятся, как только Claude и Codex заговорят.<br><br>Журнал: <code>~/.claude/interop/dialog.md</code></div>';
      }
      if (entries.length > rendered && fresh) {
        if (wasBottom) window.scrollTo({ top: document.body.scrollHeight });
        else pill.classList.add("show");
      }
      rendered = entries.length;
      const last = entries.length ? entries[entries.length - 1].time : "—";
      stat.textContent = entries.length + " записей · последняя " + last;
    }
  } catch (err) {
    dot.className = "pulse dead";
    stat.textContent = "сервер недоступен";
  }
}
// --- вкладка «сессии Codex»: полный разбор rollout-файлов ---
const alt = document.getElementById("alt");
const tabFeed = document.getElementById("tab-feed");
const tabSess = document.getElementById("tab-sess");
function setView() {
  const h = location.hash;
  const inAlt = h === "#sessions" || h.startsWith("#s=");
  feed.hidden = inAlt; alt.hidden = !inAlt; pill.classList.remove("show");
  tabFeed.classList.toggle("on", !inAlt);
  tabSess.classList.toggle("on", inAlt);
  if (h.startsWith("#s=")) loadSession(decodeURIComponent(h.slice(3)));
  else if (h === "#sessions") loadSessions();
}
window.addEventListener("hashchange", setView);
async function loadSessions() {
  alt.innerHTML = '<div class="empty">загрузка…</div>';
  const list = await (await fetch("/sessions")).json();
  alt.innerHTML = "";
  for (const s of list) {
    const a = document.createElement("a");
    a.className = "sess-row";
    a.href = "#s=" + encodeURIComponent(s.file);
    const dt = new Date(s.mtime * 1000).toLocaleString("ru-RU");
    a.innerHTML = '<div class="id">' + esc(s.name) + " · " + dt +
      (s.tokens ? " · " + Math.round(s.tokens / 1000) + "k токенов" : "") + "</div>" +
      '<div class="fu">' + esc(s.first_user || "(без пользовательских сообщений)") + "</div>";
    alt.appendChild(a);
  }
  if (!list.length) alt.innerHTML = '<div class="empty">Сессий Codex за последние дни нет.</div>';
}
async function loadSession(f) {
  alt.innerHTML = '<div class="empty">загрузка…</div>';
  const steps = await (await fetch("/session?f=" + encodeURIComponent(f))).json();
  alt.innerHTML = '<a class="backlink" href="#sessions">← все сессии</a>';
  for (const st of steps) {
    const div = document.createElement("div");
    div.className = "step " + st.kind;
    if (st.kind === "user" || st.kind === "codex") {
      div.innerHTML = '<div class="bubble"><span class="speaker s-' +
        (st.kind === "user" ? "claude" : "codex") + '">' +
        (st.kind === "user" ? "ЗАПРОС" : "CODEX") + "</span>" + esc(st.text) + "</div>";
    } else {
      div.innerHTML = '<div class="tg">' + esc(st.text) + "</div>";
    }
    alt.appendChild(div);
  }
  window.scrollTo({ top: 0 });
}
setView();

tick().then(() => { if (!location.hash) window.scrollTo({ top: document.body.scrollHeight }); });
setInterval(tick, 2000);
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = PAGE.encode("utf-8")
            ctype = "text/html; charset=utf-8"
        elif self.path == "/raw":
            try:
                body = JOURNAL.read_bytes()
            except OSError:
                body = b""
            ctype = "text/plain; charset=utf-8"
        elif self.path == "/sessions":
            body = json.dumps(list_sessions(), ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        elif self.path.startswith("/session?"):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            try:
                steps = parse_session(q.get("f", [""])[0])
            except (FileNotFoundError, OSError):
                self.send_error(404)
                return
            body = json.dumps(steps, ensure_ascii=False).encode("utf-8")
            ctype = "application/json; charset=utf-8"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass  # не засорять терминал строкой на каждый опрос


class Server(socketserver.ThreadingTCPServer):
    # allow_reuse_address намеренно False: на Windows True позволил бы
    # молча поднять второй сервер на том же порту
    daemon_threads = True


def port_taken_by_viewer() -> bool:
    """Проверяет, не наш ли просмотрщик уже слушает порт."""
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/raw", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


if __name__ == "__main__":
    import errno
    import sys
    try:
        srv = Server(("127.0.0.1", PORT), Handler)
    except OSError as e:
        if e.errno in (errno.EADDRINUSE, 10048):
            if port_taken_by_viewer():
                print(f"Уже запущен — просто открой http://127.0.0.1:{PORT}")
                sys.exit(0)
            print(f"Порт {PORT} занят другой программой — закрой её или поменяй PORT в скрипте.")
            sys.exit(1)
        raise
    with srv:
        print(f"Мост Claude<->Codex: http://127.0.0.1:{PORT}  (журнал: {JOURNAL})")
        srv.serve_forever()
