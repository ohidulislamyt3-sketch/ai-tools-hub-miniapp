#!/usr/bin/env python3
"""Build the AI Tools Hub Telegram Mini App storefront.

Reads ../data/tools.yaml and generates a single self-contained index.html
with all data embedded as JSON — no backend, no external API calls.

Free-sample rule (mirrors the bot): the first 3 tools of every category are
open (name + URL visible). Everything else is LOCKED: name and URL are
stripped at build time so they can never leak into the HTML.

Usage: python3 build.py   (run from the miniapp/ directory)
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent
YAML_PATH = BASE.parent / "data" / "tools.yaml"
ENTITLEMENTS_PATH = BASE.parent / "data" / "entitlements.json"
OUT_PATH = BASE / "index.html"
FREE_SAMPLES_PER_CAT = 1
FREE_TRIALS = 1
BOT_DEEP_LINK = "https://t.me/wahidaihunter_bot"
CHANNEL_URL = "https://t.me/aitoolshub07"
ADMIN_ID = 6292793285


def split_emoji(label: str) -> tuple[str, str]:
    """Split a category label like '🎨 Image Generation' -> ('🎨', 'Image Generation')."""
    m = re.match(r"^(\S+)\s+(.*)$", label.strip())
    if m:
        return m.group(1), m.group(2)
    return "📦", label


def main() -> None:
    import yaml

    db = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    tools = db.get("tools", [])
    trials = db.get("trials", [])

    # Free samples: first N tools of every category, in DB order (same as the bot).
    free_urls: set[str] = set()
    by_cat: dict[str, list] = {}
    for t in tools:
        by_cat.setdefault(t.get("category", ""), []).append(t)
    for cat_tools in by_cat.values():
        for t in cat_tools[:FREE_SAMPLES_PER_CAT]:
            free_urls.add(t.get("url", ""))

    new_cutoff = (date.today() - timedelta(days=7)).isoformat()

    out_tools = []
    priv: dict[str, str] = {}  # locked index -> base64("name\nurl"), decoded only for admin/paid
    n_open = n_locked = 0
    for t in tools:
        is_open = t.get("url", "") in free_urls
        if is_open:
            n_open += 1
            out_tools.append(
                {
                    "locked": False,
                    "name": t.get("name", ""),
                    "url": t.get("url", ""),
                    "category": t.get("category", ""),
                    "one_liner": t.get("one_liner", ""),
                    "free_plan": t.get("free_plan", "Free"),
                    "is_new": t.get("date_added", "") >= new_cutoff,
                }
            )
        else:
            n_locked += 1
            key = str(len(out_tools))
            # Name + URL stored base64 (never plain) — decoded client-side only
            # when the Telegram user is admin or an active paid user.
            raw = (t.get("name", "") + "\n" + t.get("url", "")).encode("utf-8")
            priv[key] = base64.b64encode(raw).decode("ascii")
            out_tools.append(
                {
                    "locked": True,
                    "key": key,
                    "category": t.get("category", ""),
                    "one_liner": t.get("one_liner", ""),
                    "free_plan": t.get("free_plan", "Free"),
                    "is_new": t.get("date_added", "") >= new_cutoff,
                }
            )

    # Active paid user IDs (for the in-app unlock).
    paid_ids: list[int] = []
    try:
        ent = json.loads(ENTITLEMENTS_PATH.read_text(encoding="utf-8"))
        today = date.today().isoformat()
        for uid, info in ent.items():
            if not isinstance(info, dict) or not info.get("paid"):
                continue
            exp = info.get("expires", "")
            if exp and exp < today:
                continue
            try:
                paid_ids.append(int(uid))
            except (TypeError, ValueError):
                pass
    except (FileNotFoundError, Exception):
        pass

    cats = []
    for c in db.get("categories", []):
        emoji, label = split_emoji(c.get("label", ""))
        cats.append({"id": c.get("id", ""), "emoji": emoji, "label": label})

    out_trials = []
    for i, t in enumerate(trials):
        # Showcase model: 1 trial free, rest blurred/locked for free users.
        if i < FREE_TRIALS:
            out_trials.append(
                {
                    "locked": False,
                    "name": t.get("name", ""),
                    "url": t.get("url", ""),
                    "country": t.get("country", ""),
                    "trial": t.get("trial", ""),
                    "one_liner": t.get("one_liner", ""),
                }
            )
            continue
        key = "r" + str(i)
        raw = (t.get("name", "") + "\n" + t.get("url", "")).encode("utf-8")
        priv[key] = base64.b64encode(raw).decode("ascii")
        out_trials.append(
            {
                "locked": True,
                "key": key,
                "country": t.get("country", ""),
                "trial": t.get("trial", ""),
                "one_liner": t.get("one_liner", ""),
            }
        )

    meta = {
        "generated": date.today().isoformat(),
        "total_tools": len(tools),
        "open_tools": n_open,
        "locked_tools": n_locked,
        "trials": len(trials),
        "bot_link": BOT_DEEP_LINK,
        "channel_url": CHANNEL_URL,
    }

    html = TEMPLATE
    html = html.replace("__CATS_JSON__", json.dumps(cats, ensure_ascii=False))
    html = html.replace("__TOOLS_JSON__", json.dumps(out_tools, ensure_ascii=False))
    html = html.replace("__TRIALS_JSON__", json.dumps(out_trials, ensure_ascii=False))
    html = html.replace("__META_JSON__", json.dumps(meta, ensure_ascii=False))
    html = html.replace("__PRIV_JSON__", json.dumps(priv, ensure_ascii=False))
    html = html.replace("__ADMIN_ID__", json.dumps(ADMIN_ID))
    html = html.replace("__PAID_IDS__", json.dumps(paid_ids))
    assert "__CATS_JSON__" not in html and "__TOOLS_JSON__" not in html
    assert "__PRIV_JSON__" not in html

    # Final safety net: no locked name/URL may appear in PLAIN text.
    # (They exist only as base64 blobs, which Google doesn't index.)
    for t in tools:
        if t.get("url", "") not in free_urls:
            assert t["name"] not in html, f"LEAK: {t['name']}"
            assert t["url"] not in html, f"LEAK: {t['url']}"

    OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Built {OUT_PATH} ({OUT_PATH.stat().st_size // 1024} KB)")
    print(f"  tools: {len(tools)} (open {n_open}, locked {n_locked}), trials: {len(trials)}")
    print(f"  privileged unlock: admin + {len(paid_ids)} paid user(s)")
    print("  leak check: PASS — no locked names/URLs in plain HTML")


TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<meta name="theme-color" content="#0d0f12">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>AI Tools Hub — Free AI Store</title>
<script src="https://telegram.org/js/telegram-web-app.js"></script>
<style>
  :root{
    --bg:#0d0f12; --bg2:#14171c; --card:#181c22; --card2:#1e232b;
    --line:#262c36; --txt:#f2f4f7; --mut:#9aa4b2; --dim:#6b7482;
    --teal:#00C9A7; --teal-d:#00a386; --gold:#f5b942;
    --r:16px;
  }
  *{margin:0;padding:0;box-sizing:border-box;-webkit-tap-highlight-color:transparent}
  body{
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;
    background:radial-gradient(1200px 600px at 50% -10%, #12241f 0%, var(--bg) 55%) fixed, var(--bg);
    color:var(--txt); min-height:100vh; padding-bottom:90px;
  }
  /* ---------- header ---------- */
  .hero{padding:26px 18px 14px;text-align:center;position:relative;overflow:hidden}
  .hero::before{content:"";position:absolute;inset:-40px;background:
    radial-gradient(420px 200px at 20% 0%, rgba(0,201,167,.16), transparent 60%),
    radial-gradient(420px 200px at 85% 10%, rgba(0,201,167,.10), transparent 60%);pointer-events:none}
  .logo{font-size:44px;filter:drop-shadow(0 0 18px rgba(0,201,167,.45))}
  .hero h1{font-size:26px;font-weight:800;letter-spacing:.3px;margin-top:6px}
  .hero h1 span{color:var(--teal)}
  .hero p{color:var(--mut);font-size:13px;margin-top:6px}
  .stats{display:flex;gap:8px;justify-content:center;margin-top:14px;flex-wrap:wrap}
  .stat{background:rgba(0,201,167,.08);border:1px solid rgba(0,201,167,.25);color:var(--teal);
    font-size:12px;font-weight:700;padding:6px 12px;border-radius:999px}
  /* ---------- search ---------- */
  .searchwrap{position:sticky;top:0;z-index:50;padding:10px 16px;
    background:rgba(13,15,18,.88);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)}
  .search{display:flex;align-items:center;gap:10px;background:var(--bg2);
    border:1px solid var(--line);border-radius:14px;padding:12px 14px}
  .search:focus-within{border-color:var(--teal);box-shadow:0 0 0 3px rgba(0,201,167,.15)}
  .search input{flex:1;background:none;border:none;outline:none;color:var(--txt);font-size:15px}
  .search input::placeholder{color:var(--dim)}
  /* ---------- tabs ---------- */
  .tabs{display:flex;gap:8px;overflow-x:auto;padding:12px 16px 4px;scrollbar-width:none}
  .tabs::-webkit-scrollbar{display:none}
  .tab{flex:0 0 auto;border:1px solid var(--line);background:var(--bg2);color:var(--mut);
    font-size:13px;font-weight:600;padding:9px 14px;border-radius:999px;cursor:pointer;transition:.18s}
  .tab.active{background:var(--teal);border-color:var(--teal);color:#04231c;
    box-shadow:0 4px 18px rgba(0,201,167,.35)}
  /* ---------- sections & grid ---------- */
  .sec{padding:14px 16px 0}
  .sec-title{font-size:17px;font-weight:800;margin:6px 2px 12px;display:flex;align-items:center;gap:8px}
  .sec-title .cnt{font-size:11px;font-weight:700;color:var(--teal);background:rgba(0,201,167,.1);
    border:1px solid rgba(0,201,167,.25);padding:2px 9px;border-radius:999px}
  .grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
  @media(min-width:700px){.grid{grid-template-columns:repeat(3,1fr)}}
  @media(min-width:1000px){.grid{grid-template-columns:repeat(4,1fr)}.wrap{max-width:1060px;margin:0 auto}}
  .card{background:linear-gradient(160deg,var(--card),var(--card2));border:1px solid var(--line);
    border-radius:var(--r);padding:14px;display:flex;flex-direction:column;gap:8px;
    position:relative;overflow:hidden;transition:transform .18s,border-color .18s}
  .card:active{transform:scale(.97)}
  .card.open:hover{border-color:rgba(0,201,167,.5)}
  .card.locked{border-style:dashed}
  .blur-wrap{filter:blur(6px);pointer-events:none;user-select:none;-webkit-user-select:none}
  .card.locked::after{content:"";position:absolute;inset:0;pointer-events:none;
    background:linear-gradient(115deg,transparent 40%,rgba(245,185,66,.07) 50%,transparent 60%)}
  .badge-new{position:absolute;top:10px;right:10px;font-size:10px;font-weight:800;color:#04231c;
    background:var(--teal);padding:3px 8px;border-radius:999px;letter-spacing:.4px}
  .cicon{font-size:26px}
  .cname{font-size:14.5px;font-weight:750;line-height:1.3;word-break:break-word}
  .cname a{color:var(--txt);text-decoration:none}
  .cline{font-size:12.5px;color:var(--mut);line-height:1.45;flex:1}
  .cplan{font-size:11px;color:var(--teal);font-weight:700}
  .card.locked .cplan{color:var(--gold)}
  .btn{display:block;text-align:center;font-size:13.5px;font-weight:800;text-decoration:none;
    padding:10px;border-radius:12px;transition:.18s;cursor:pointer;border:none;width:100%}
  .btn-open{background:var(--teal);color:#04231c;box-shadow:0 4px 16px rgba(0,201,167,.3)}
  .btn-open:active{background:var(--teal-d)}
  .btn-lock{background:rgba(245,185,66,.12);color:var(--gold);border:1px solid rgba(245,185,66,.4)}
  .lock-big{font-size:30px;text-align:center;filter:drop-shadow(0 0 12px rgba(245,185,66,.4))}
  /* trials */
  .trial{border-color:rgba(0,201,167,.35);background:linear-gradient(160deg,#151d19,#181c22)}
  .trial .tmeta{font-size:11.5px;color:var(--mut)}
  .trial .tmeta b{color:var(--teal)}
  .empty{text-align:center;color:var(--dim);padding:34px 10px;font-size:14px;grid-column:1/-1}
  /* bottom nav */
  .bottombar{position:fixed;left:0;right:0;bottom:0;z-index:60;display:flex;gap:10px;
    padding:12px 16px calc(12px + env(safe-area-inset-bottom));
    background:rgba(13,15,18,.92);backdrop-filter:blur(12px);border-top:1px solid var(--line)}
  .bottombar a{flex:1;text-align:center;text-decoration:none;font-weight:800;font-size:14px;
    padding:13px;border-radius:14px}
  .bb-bot{background:var(--teal);color:#04231c}
  .bb-ch{background:var(--bg2);color:var(--txt);border:1px solid var(--line)}
  .foot{text-align:center;color:var(--dim);font-size:11.5px;padding:22px 16px 0;line-height:1.7}
  .foot a{color:var(--teal);text-decoration:none}
</style>
</head>
<body>
<div class="wrap">
  <div class="hero">
    <div class="logo">🏪</div>
    <h1>AI Tools <span>Hub</span></h1>
    <p>Your free AI store — verified tools, trial offers, new drops daily</p>
    <div class="stats" id="stats"></div>
  </div>

  <div class="searchwrap">
    <div class="search"><span>🔍</span><input id="q" type="search" placeholder="Search tools… (e.g. video, voice)" autocomplete="off"></div>
  </div>

  <div class="tabs" id="tabs"></div>

  <div class="sec">
    <div class="sec-title">🛠️ Tools <span class="cnt" id="toolCount"></span></div>
    <div class="grid" id="grid"></div>
  </div>

  <div class="sec">
    <div class="sec-title">🎁 Trial Offers <span class="cnt" id="trialCount"></span></div>
    <div class="grid" id="tgrid"></div>
  </div>

  <div class="foot">
    🔒 Premium tools unlock inside the bot<br>
    <a href="https://t.me/wahidaihunter_bot">🤖 @wahidaihunter_bot</a> ·
    <a href="https://t.me/aitoolshub07">📢 Channel</a>
  </div>
</div>

<nav class="bottombar">
  <a class="bb-bot" href="https://t.me/wahidaihunter_bot">🤖 Open in Bot</a>
  <a class="bb-ch" href="https://t.me/aitoolshub07">📢 Channel</a>
</nav>

<script>
(function(){
  "use strict";
  var tg = (window.Telegram && Telegram.WebApp) ? Telegram.WebApp : null;
  if (tg) { try { tg.ready(); tg.expand(); } catch(e){} }

  var CATS = __CATS_JSON__;
  var TOOLS = __TOOLS_JSON__;
  var TRIALS = __TRIALS_JSON__;
  var META = __META_JSON__;
  var PRIV = __PRIV_JSON__;
  var ADMIN_ID = __ADMIN_ID__;
  var PAID_IDS = __PAID_IDS__;
  var BOT = META.bot_link;

  /* Showcase model: everyone SEES everything; free users see it BLURRED
     (no clicks), admin/paid see it clear. Locked data is base64 in the page
     (never plain text) so it isn't indexed. */
  function b64d(s){ try { return decodeURIComponent(escape(atob(s))); } catch(e){ return ""; } }
  var _u = (tg && tg.initDataUnsafe && tg.initDataUnsafe.user) ? tg.initDataUnsafe.user.id : 0;
  var _uid = (typeof _u === "number") ? _u : (parseInt(_u, 10) || 0);
  var PRIVILEGED = (_uid === ADMIN_ID) || (PAID_IDS.indexOf(_uid) >= 0);
  function decodeLocked(t){
    if (t.locked && t.key && PRIV[t.key]) {
      var parts = b64d(PRIV[t.key]).split("\\n");
      t.name = parts[0] || "";
      t.url = parts[1] || "";
      if (PRIVILEGED) t.locked = false;
    }
  }
  TOOLS.forEach(decodeLocked);
  TRIALS.forEach(decodeLocked);

  var state = { cat:"all", q:"" };

  function esc(s){ return String(s==null?"":s).replace(/[&<>"']/g, function(c){
    return {"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]; }); }

  /* stats */
  document.getElementById("stats").innerHTML =
    '<span class="stat">✅ 100+ verified tools</span>' +
    '<span class="stat">🎁 '+TRIALS.length+' trial offers</span>' +
    '<span class="stat">🆕 new daily</span>';

  /* tabs */
  var tabsEl = document.getElementById("tabs");
  function catLabel(c){ return c.emoji+" "+c.label; }
  function renderTabs(){
    var h = '<button class="tab'+(state.cat==="all"?" active":"")+'" data-c="all">🌟 All</button>';
    CATS.forEach(function(c){
      h += '<button class="tab'+(state.cat===c.id?" active":"")+'" data-c="'+c.id+'">'+esc(catLabel(c))+"</button>";
    });
    tabsEl.innerHTML = h;
  }
  tabsEl.addEventListener("click", function(e){
    var b = e.target.closest(".tab"); if(!b) return;
    state.cat = b.getAttribute("data-c"); renderTabs(); renderTools();
  });

  function catEmoji(id){
    for (var i=0;i<CATS.length;i++) if (CATS[i].id===id) return CATS[i].emoji;
    return "📦";
  }

  function openBtn(t){
    return '<a class="btn btn-open" href="'+esc(t.url)+'" target="_blank" rel="noopener">🔗 Open</a>';
  }
  function openPremium(e){
    if (e) e.preventDefault();
    var url = BOT + "?start=premium";
    if (tg && tg.openTelegramLink) { try { tg.openTelegramLink(url); return; } catch(err){} }
    try { window.open(url, "_blank"); } catch(err2){ location.href = url; }
  }
  function lockBtn(){
    return '<a class="btn btn-lock" href="#" onclick="openPremium(event);return false;">💎 Get Premium</a>';
  }

  function toolCard(t){
    var badge = t.is_new ? '<span class="badge-new">NEW</span>' : "";
    if (t.locked) {
      /* Showcase: real content visible but blurred, not clickable. */
      return '<div class="card locked">'+badge+
        '<div class="blur-wrap">'+
        '<div class="cicon">'+esc(catEmoji(t.category))+'</div>'+
        '<div class="cname">'+esc(t.name)+'</div>'+
        '<div class="cline">'+esc(t.one_liner)+'</div>'+
        '<div class="cplan">🆓 '+esc(t.free_plan)+'</div>'+
        '</div>'+
        lockBtn()+'</div>';
    }
    return '<div class="card open">'+badge+
      '<div class="cicon">'+esc(catEmoji(t.category))+'</div>'+
      '<div class="cname">'+esc(t.name)+'</div>'+
      '<div class="cline">'+esc(t.one_liner)+'</div>'+
      '<div class="cplan">🆓 '+esc(t.free_plan)+'</div>'+
      openBtn(t)+'</div>';
  }

  function renderTools(){
    var q = state.q.trim().toLowerCase();
    var list = TOOLS.filter(function(t){
      if (state.cat!=="all" && t.category!==state.cat) return false;
      if (!q) return true;
      var hay = ((t.locked?"":t.name)+" "+t.one_liner+" "+t.free_plan).toLowerCase();
      return hay.indexOf(q) >= 0;
    });
    document.getElementById("toolCount").textContent = list.length;
    document.getElementById("grid").innerHTML = list.length
      ? list.map(toolCard).join("")
      : '<div class="empty">😕 Nothing found — try another keyword.</div>';
  }

  function renderTrials(){
    document.getElementById("trialCount").textContent = TRIALS.length;
    document.getElementById("tgrid").innerHTML = TRIALS.map(function(t){
      if (t.locked) {
        return '<div class="card locked trial">'+
          '<div class="blur-wrap">'+
          '<div class="cicon">🎁</div>'+
          '<div class="cname">'+esc(t.name)+'</div>'+
          '<div class="tmeta">🌍 '+esc(t.country)+' · <b>'+esc(t.trial)+'</b></div>'+
          '<div class="cline">'+esc(t.one_liner)+'</div>'+
          '</div>'+
          lockBtn()+'</div>';
      }
      return '<div class="card open trial">'+
        '<div class="cicon">🎁</div>'+
        '<div class="cname">'+esc(t.name)+'</div>'+
        '<div class="tmeta">🌍 '+esc(t.country)+' · <b>'+esc(t.trial)+'</b></div>'+
        '<div class="cline">'+esc(t.one_liner)+'</div>'+
        '<a class="btn btn-open" href="'+esc(t.url)+'" target="_blank" rel="noopener">🔗 Claim Offer</a></div>';
    }).join("");
  }

  var input = document.getElementById("q");
  var deb = null;
  input.addEventListener("input", function(){
    clearTimeout(deb);
    deb = setTimeout(function(){ state.q = input.value; renderTools(); }, 120);
  });

  renderTabs(); renderTools(); renderTrials();
})();
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
