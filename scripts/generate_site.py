"""Generate the static Guoxue x AI intelligence dashboard."""

from __future__ import annotations

import html
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
CONFIG_FILE = ROOT / "site.config.json"
MATERIALS_FILE = ROOT / "content" / "materials.json"
TOPICS_FILE = ROOT / "content" / "topics.json"
HISTORY_DIR = ROOT / "content" / "history"
PUBLIC_HISTORY_DIR = PUBLIC / "history"
TIMEZONE = timezone(timedelta(hours=8))


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def fmt_date(value: str) -> str:
    try:
        day = datetime.strptime(value, "%Y-%m-%d")
        return f"{day.year}年{day.month}月{day.day}日"
    except ValueError:
        return value


def safe_url(value: str) -> str:
    return esc(value if value.startswith(("https://", "http://")) else "#")


def archive_report(report: dict) -> None:
    report_date = report.get("report_date", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        return
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    target = HISTORY_DIR / f"{report_date}.json"
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


CSS = r"""
:root{--paper:#f3f0e8;--paper2:#ebe6da;--ink:#18211d;--muted:#6e746f;--jade:#0d6452;--jade2:#17483f;--red:#a33a2b;--gold:#b88b44;--line:rgba(24,33,29,.13);--card:#fbfaf6;--shadow:0 18px 48px rgba(36,42,33,.09)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,"Noto Sans SC","PingFang SC","Microsoft YaHei",sans-serif;line-height:1.6}body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.2;background-image:radial-gradient(#516057 0.65px,transparent .65px);background-size:8px 8px}a{color:inherit;text-decoration:none}h1,h2,h3,p{margin:0}.topbar{position:sticky;top:0;z-index:20;border-bottom:1px solid var(--line);background:rgba(243,240,232,.9);backdrop-filter:blur(16px)}.topbar-inner{width:min(1240px,calc(100% - 40px));min-height:68px;margin:auto;display:flex;align-items:center;justify-content:space-between;gap:22px}.brand{display:flex;align-items:center;gap:11px;font-weight:900;letter-spacing:.02em}.seal{width:36px;height:36px;display:grid;place-items:center;background:var(--red);border-radius:4px;color:#fff;font-family:serif;font-size:12px;line-height:1.05;box-shadow:inset 0 0 0 2px rgba(255,255,255,.35)}nav{display:flex;gap:22px;color:var(--muted);font-size:14px}nav a:hover{color:var(--jade)}main{width:min(1240px,calc(100% - 40px));margin:28px auto 64px}.hero{position:relative;overflow:hidden;padding:54px clamp(26px,5vw,68px);border-radius:24px;background:linear-gradient(125deg,#102c26,#164c40 62%,#80612d);color:#fff;box-shadow:var(--shadow)}.hero:after{content:"AI";position:absolute;right:-16px;bottom:-96px;color:rgba(255,255,255,.055);font:900 260px/1 Georgia,serif}.eyebrow{color:#d9be84;font-size:12px;font-weight:900;letter-spacing:.16em;text-transform:uppercase}.hero h1{max-width:820px;margin-top:11px;font-family:"Songti SC","STSong",serif;font-size:clamp(40px,7vw,78px);line-height:1.05;letter-spacing:-.03em}.hero .lead{max-width:720px;margin-top:20px;color:rgba(255,255,255,.76);font-size:17px}.pulse{display:inline-flex;align-items:center;gap:8px;margin-top:24px;padding:7px 12px;border:1px solid rgba(255,255,255,.2);border-radius:999px;color:rgba(255,255,255,.78);font-size:12px}.pulse i{width:7px;height:7px;border-radius:50%;background:#71d7a7;box-shadow:0 0 0 5px rgba(113,215,167,.12)}.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}.stat{padding:20px 22px;border:1px solid var(--line);border-radius:14px;background:rgba(251,250,246,.85);box-shadow:var(--shadow)}.stat strong{display:block;font:700 32px/1.1 Georgia,serif}.stat span{display:block;margin-top:6px;color:var(--muted);font-size:12px}.toolbar{position:sticky;top:69px;z-index:15;display:grid;grid-template-columns:1fr;gap:10px;margin:22px 0;padding:12px;border:1px solid var(--line);border-radius:14px;background:rgba(243,240,232,.94);backdrop-filter:blur(15px)}.search{width:100%;padding:11px 14px;border:1px solid var(--line);border-radius:9px;background:#fff;font:inherit;color:var(--ink);outline:none}.search:focus{border-color:var(--jade)}.filters{display:flex;flex-wrap:wrap;gap:7px}.filter{border:1px solid var(--line);border-radius:999px;padding:9px 13px;background:transparent;color:var(--muted);cursor:pointer;font-weight:700}.filter.active{border-color:var(--jade);background:var(--jade);color:white}.section{margin-top:38px}.section-head{display:flex;justify-content:space-between;align-items:end;gap:16px;margin-bottom:15px}.section-head h2{font-family:"Songti SC",serif;font-size:30px}.section-head p{color:var(--muted);font-size:13px}.feed{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.card{position:relative;min-height:265px;display:flex;flex-direction:column;padding:22px;border:1px solid var(--line);border-radius:16px;background:var(--card);box-shadow:var(--shadow);transition:.2s ease}.card:hover{transform:translateY(-3px);border-color:rgba(13,100,82,.38)}.card.hide{display:none}.card-top{display:flex;justify-content:space-between;align-items:center;gap:8px}.badges{display:flex;flex-wrap:wrap;gap:6px}.badge{padding:3px 9px;border-radius:999px;background:rgba(13,100,82,.09);color:var(--jade);font-size:11px;font-weight:900}.badge.topic-国学{background:rgba(163,58,43,.09);color:var(--red)}.badge.topic-国学×AI{background:rgba(184,139,68,.14);color:#886018}.date{color:var(--muted);font-size:11px}.card h3{margin-top:15px;font-size:18px;line-height:1.45}.summary{margin-top:10px;color:var(--muted);font-size:13px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}.card-foot{display:flex;justify-content:space-between;align-items:end;gap:12px;margin-top:auto;padding-top:18px}.source{max-width:70%;color:var(--muted);font-size:11px}.open{color:var(--jade);font-size:13px;font-weight:900}.empty{grid-column:1/-1;padding:42px;border:1px dashed var(--line);border-radius:16px;text-align:center;color:var(--muted)}.source-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.source-card{padding:19px;border:1px solid var(--line);border-radius:14px;background:var(--card)}.source-card .row{display:flex;justify-content:space-between;gap:8px}.source-card h3{font-size:16px}.source-card p{margin-top:6px;color:var(--muted);font-size:12px}.status{display:inline-flex;align-items:center;gap:6px;color:var(--muted);font-size:11px}.dot{width:7px;height:7px;border-radius:50%;background:#aeb4af}.dot.ok{background:#258665}.dot.bad{background:#b84a3b}.panel{padding:26px;border:1px solid var(--line);border-radius:16px;background:var(--card);box-shadow:var(--shadow)}.topic-list,.archive-list{display:grid;gap:10px}.topic-row,.archive-row{display:grid;grid-template-columns:120px 1fr auto;gap:18px;align-items:center;padding:16px 0;border-top:1px solid var(--line)}.topic-row:first-child,.archive-row:first-child{border-top:0}.muted{color:var(--muted);font-size:13px}footer{margin-top:44px;padding-top:20px;border-top:1px solid var(--line);color:var(--muted);font-size:12px}.noscript{padding:12px;background:#fff0d2;color:#6d4b0e;text-align:center}.hidden-count{font-variant-numeric:tabular-nums}
@media(max-width:980px){.feed{grid-template-columns:repeat(2,1fr)}.source-grid{grid-template-columns:repeat(3,1fr)}.toolbar{grid-template-columns:1fr}.toolbar{position:static}}
@media(max-width:680px){.topbar-inner,main{width:min(100% - 24px,1240px)}.topbar-inner{align-items:flex-start;flex-direction:column;padding:13px 0}nav{width:100%;justify-content:space-between;gap:8px}.hero{padding:38px 24px;border-radius:18px}.hero:after{font-size:160px}.stats{grid-template-columns:repeat(2,1fr)}.feed,.source-grid{grid-template-columns:1fr}.section-head{align-items:flex-start;flex-direction:column}.topic-row,.archive-row{grid-template-columns:1fr;gap:5px}}
"""

FILTER_JS = r"""
<script>
const state={topic:'全部',platform:'全部'};
const cards=[...document.querySelectorAll('.card[data-topic]')];
const query=document.querySelector('#q');
function apply(){const q=(query?.value||'').trim().toLowerCase();let visible=0;cards.forEach(card=>{const okTopic=state.topic==='全部'||card.dataset.topic===state.topic;const okPlatform=state.platform==='全部'||card.dataset.platform===state.platform;const okQuery=!q||card.innerText.toLowerCase().includes(q);const show=okTopic&&okPlatform&&okQuery;card.classList.toggle('hide',!show);if(show)visible++;});document.querySelector('#visible').textContent=visible;document.querySelector('#no-results').style.display=visible?'none':'block'}
document.querySelectorAll('[data-filter]').forEach(button=>button.addEventListener('click',()=>{const group=button.dataset.filter;state[group]=button.dataset.value;document.querySelectorAll(`[data-filter="${group}"]`).forEach(x=>x.classList.toggle('active',x===button));apply()}));
query?.addEventListener('input',apply);apply();
</script>
"""


def nav() -> str:
    return '<a href="./">今日情报</a><a href="sources.html">平台矩阵</a><a href="topics.html">选题库</a><a href="archive.html">归档</a>'


def shell(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="聚合各大平台的国学、AI及国学×AI公开信息"><title>{esc(title)}</title><style>{CSS}</style></head><body><header class="topbar"><div class="topbar-inner"><a class="brand" href="./"><span class="seal">国学<br>AI</span><span>国学 × AI 情报站</span></a><nav>{nav()}</nav></div></header><main>{body}</main></body></html>"""


def item_card(item: dict) -> str:
    topic = item.get("topic") or "AI"
    platform = item.get("platform") or "其他"
    search_blob = " ".join(str(item.get(k, "")) for k in ("title", "summary", "source", "kind"))
    return f"""<article class="card" data-topic="{esc(topic)}" data-platform="{esc(platform)}" data-search="{esc(search_blob)}"><div class="card-top"><div class="badges"><span class="badge topic-{esc(topic)}">{esc(topic)}</span><span class="badge">{esc(platform)}</span><span class="badge">{esc(item.get('kind'))}</span></div><span class="date">{esc(item.get('published'))}</span></div><h3>{esc(item.get('title'))}</h3><p class="summary">{esc(item.get('summary') or '点击查看原始内容与上下文。')}</p><div class="card-foot"><span class="source">来源：{esc(item.get('source') or platform)}</span><a class="open" href="{safe_url(item.get('url',''))}" target="_blank" rel="noopener noreferrer">阅读原文 ↗</a></div></article>"""


def render_index(config: dict, report: dict, now: datetime) -> str:
    items = report.get("items") or []
    platforms = sorted({str(i.get("platform")) for i in items if i.get("platform")})
    topics = ["国学", "AI", "国学×AI"]
    counts = Counter(i.get("topic") for i in items)
    cards = "".join(item_card(i) for i in items)
    if not cards:
        cards = '<div class="empty">本次未抓取到内容。可到「平台矩阵」查看各来源状态。</div>'
    topic_buttons = "".join(f'<button class="filter" data-filter="topic" data-value="{esc(t)}">{esc(t)}</button>' for t in topics)
    platform_buttons = "".join(f'<button class="filter" data-filter="platform" data-value="{esc(p)}">{esc(p)}</button>' for p in platforms)
    generated = report.get("generated_at") or now.isoformat(timespec="minutes")
    body = f"""<section class="hero"><p class="eyebrow">Guoxue × Artificial Intelligence Radar</p><h1>{esc(config.get('site_name'))}</h1><p class="lead">{esc(config.get('tagline'))}</p><span class="pulse"><i></i>最近更新：{esc(generated.replace('T',' '))}</span></section><section class="stats"><div class="stat"><strong>{len(items)}</strong><span>本期公开信息</span></div><div class="stat"><strong>{len(platforms)}</strong><span>已捕获平台</span></div><div class="stat"><strong>{counts['国学']}</strong><span>国学</span></div><div class="stat"><strong>{counts['AI'] + counts['国学×AI']}</strong><span>AI 与交叉内容</span></div></section><section class="toolbar"><input id="q" class="search" type="search" placeholder="搜索人物、概念、平台或标题…" aria-label="搜索情报"><div class="filters"><button class="filter active" data-filter="topic" data-value="全部">全部主题</button>{topic_buttons}</div><div class="filters"><button class="filter active" data-filter="platform" data-value="全部">全部平台</button>{platform_buttons}</div></section><section class="section"><div class="section-head"><h2>今日情报流</h2><p>当前显示 <span id="visible" class="hidden-count">{len(items)}</span> 条 · 点击卡片原文可回到信息源核验</p></div><div class="feed">{cards}<div class="empty" id="no-results" style="display:none">没有匹配结果，换个关键词或筛选条件试试。</div></div></section><footer>信息来自公开页面与 RSS 检索结果；本站只做索引、摘要和分类，版权归原作者与平台所有。生成时间：{esc(now.strftime('%Y-%m-%d %H:%M'))} Asia/Shanghai。</footer>{FILTER_JS}"""
    return shell(config.get("site_name", "国学 × AI 全网情报站"), body)


def render_sources(config: dict, report: dict, now: datetime) -> str:
    status_map = {s.get("platform"): s for s in report.get("source_status", [])}
    cards = []
    for source in config.get("sources", []):
        status = status_map.get(source.get("name"), {})
        if status:
            state_class = "ok" if status.get("ok") else "bad"
            state_text = f"本次 {status.get('count',0)} 条" if status.get("ok") else "本次连接失败"
        else:
            state_class, state_text = "", "等待首次定时采集"
        search_url = "https://www.google.com/search?q=" + __import__("urllib.parse", fromlist=["quote"]).quote(f"site:{source.get('domain')} {source.get('query')}")
        cards.append(f"""<a class="source-card" href="{esc(search_url)}" target="_blank" rel="noopener noreferrer"><div class="row"><h3>{esc(source.get('name'))}</h3><span class="status"><i class="dot {state_class}"></i>{esc(state_text)}</span></div><p>{esc(source.get('kind'))} · {esc(source.get('domain'))}</p><p>关键词：{esc(source.get('query'))}</p></a>""")
    body = f"""<section class="hero"><p class="eyebrow">Source Matrix</p><h1>平台矩阵</h1><p class="lead">覆盖中文内容生态、全球社区与研究平台。绿点表示最近一次采集成功，红点表示该来源临时不可达。</p></section><section class="section"><div class="section-head"><h2>{len(cards)} 个公开来源</h2><p>站点不登录账号，不采集私域内容</p></div><div class="source-grid">{''.join(cards)}</div></section><section class="section panel"><h2>采集边界</h2><p class="muted" style="margin-top:10px">通过公开搜索 RSS 建立索引；不绕过登录、验证码、反爬或付费墙。平台搜索结果会受搜索引擎收录影响，因此“0 条”不等于平台当天没有相关内容。每条信息都保留原始链接，建议发布或引用前回源核验。</p></section><footer>页面生成：{esc(now.strftime('%Y-%m-%d %H:%M'))} Asia/Shanghai。</footer>"""
    return shell("平台矩阵 · 国学 × AI 情报站", body)


def render_topics(config: dict, topics: list[dict], report: dict, now: datetime) -> str:
    rows = []
    for topic in topics:
        rows.append(f"""<div class="topic-row"><strong>{esc(topic.get('status') or '待做')}</strong><div><h3>{esc(topic.get('title'))}</h3><p class="muted">{esc(topic.get('notes'))}</p></div><span class="muted">{esc(topic.get('planned_date'))}</span></div>""")
    if not rows:
        for item in (report.get("items") or [])[:8]:
            rows.append(f"""<div class="topic-row"><strong>灵感</strong><div><h3>{esc(item.get('title'))}</h3><p class="muted">来源：{esc(item.get('platform'))} · {esc(item.get('topic'))}</p></div><a class="open" href="{safe_url(item.get('url',''))}" target="_blank" rel="noopener noreferrer">看原文 ↗</a></div>""")
    content = "".join(rows) or '<div class="empty">暂无选题，完成首次采集后会自动显示情报灵感。</div>'
    body = f"""<section class="hero"><p class="eyebrow">Editorial Pipeline</p><h1>选题库</h1><p class="lead">把高价值信号变成可执行的内容题目。未维护人工选题时，这里自动展示最新情报作为灵感。</p></section><section class="section panel"><div class="topic-list">{content}</div></section><footer>页面生成：{esc(now.strftime('%Y-%m-%d %H:%M'))} Asia/Shanghai。</footer>"""
    return shell("选题库 · 国学 × AI 情报站", body)


def report_count(report: dict) -> int:
    if "items" in report:
        return len(report.get("items") or [])
    return sum(len(report.get(k) or []) for k in ("competitor_ads", "pain_points", "trends"))


def render_archive(now: datetime) -> str:
    rows = []
    for path in sorted(HISTORY_DIR.glob("????-??-??.json"), reverse=True):
        report = load_json(path, {})
        if not report:
            continue
        count = report_count(report)
        rows.append(f"""<div class="archive-row"><strong>{esc(report.get('report_date'))}</strong><div><h3>{count} 条记录</h3><p class="muted">结构化快照，可用于复盘平台与主题变化。</p></div><a class="open" href="history/{esc(path.name)}" target="_blank">查看 JSON ↗</a></div>""")
    body = f"""<section class="hero"><p class="eyebrow">Knowledge Archive</p><h1>情报归档</h1><p class="lead">按日期保存每次情报快照，为内容复盘、趋势判断和长期研究留下可追溯数据。</p></section><section class="section panel"><div class="archive-list">{''.join(rows) or '<div class="empty">暂无归档。</div>'}</div></section><footer>页面生成：{esc(now.strftime('%Y-%m-%d %H:%M'))} Asia/Shanghai。</footer>"""
    return shell("情报归档 · 国学 × AI 情报站", body)


def main() -> None:
    now = datetime.now(TIMEZONE)
    config = load_json(CONFIG_FILE, {})
    report = load_json(MATERIALS_FILE, {"items": []})
    topics = load_json(TOPICS_FILE, {"topics": []}).get("topics", [])
    PUBLIC.mkdir(exist_ok=True)
    archive_report(report)
    PUBLIC_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    for source in HISTORY_DIR.glob("????-??-??.json"):
        shutil.copy2(source, PUBLIC_HISTORY_DIR / source.name)
    (PUBLIC / "index.html").write_text(render_index(config, report, now), encoding="utf-8")
    (PUBLIC / "sources.html").write_text(render_sources(config, report, now), encoding="utf-8")
    (PUBLIC / "topics.html").write_text(render_topics(config, topics, report, now), encoding="utf-8")
    (PUBLIC / "archive.html").write_text(render_archive(now), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    print(f"generated {len(report.get('items') or [])} item(s) across {len(config.get('sources') or [])} configured sources")


if __name__ == "__main__":
    main()
