"""出海内容素材雷达 - 静态站点生成器。

数据来源（全部由人工或 AI 助手维护，脚本只负责渲染）：
- site.config.json       站点配置：赛道、竞品、关键词
- content/materials.json 每日素材：竞品广告 / 用户痛点 / 趋势信号
- content/topics.json    选题库：从素材沉淀的可执行选题
- content/history/       每日素材的自动归档

输出到 public/：index.html（素材流）、topics.html（选题库）、archive.html（沉淀库）。
"""

import html
import json
import re
import shutil
import sys
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
MAX_REPORT_AGE_DAYS = 7

TOPIC_STATUSES = ["待做", "进行中", "已发布", "已验证"]
TREND_SIGNALS = {"上升": "signal-up", "热议": "signal-hot", "下降": "signal-down"}


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{path} 不是合法的 JSON：{exc}")


def check_report_freshness(report_date: str, now: datetime) -> None:
    """7 天内允许重新发布（模板/配置更新），超过 7 天视为过期拒绝部署。"""
    today = now.strftime("%Y-%m-%d")
    try:
        report_day = datetime.strptime(report_date, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
    except (TypeError, ValueError):
        raise RuntimeError(f"report_date {report_date!r} 不是合法的 YYYY-MM-DD 日期")
    age_days = (now.date() - report_day.date()).days
    if age_days < 0 or age_days > MAX_REPORT_AGE_DAYS:
        raise RuntimeError(
            f"素材报告日期 {report_date!r} 距今天 {today} 已 {age_days} 天，"
            f"超过 {MAX_REPORT_AGE_DAYS} 天视为过期，保留线上已有版本。"
        )
    if age_days > 0:
        print(
            f"warn: materials report is {age_days} day(s) old ({report_date}); "
            "republishing with the latest site template.",
            file=sys.stderr,
        )


def archive_materials(report: dict) -> None:
    report_date = report.get("report_date", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        raise ValueError(f"Invalid report_date for archive: {report_date!r}")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{report_date}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_history() -> list[dict]:
    reports = []
    if not HISTORY_DIR.exists():
        return reports
    for path in sorted(HISTORY_DIR.glob("????-??-??.json"), reverse=True):
        try:
            report = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(report, dict) and report.get("report_date"):
            reports.append(report)
    return reports


def esc(value) -> str:
    return html.escape(str(value or ""))


def fmt_date(report_date: str) -> str:
    try:
        day = datetime.strptime(report_date, "%Y-%m-%d")
        return f"{day.year}年{day.month}月{day.day}日"
    except ValueError:
        return report_date


def history_entry_count(report: dict) -> int:
    if "items" in report:  # 旧版资讯归档
        return len(report.get("items") or [])
    return sum(
        len(report.get(key) or [])
        for key in ("competitor_ads", "pain_points", "trends")
    )


def history_entry_summary(report: dict) -> str:
    if report.get("trend"):  # 旧版资讯归档
        return report["trend"]
    parts = []
    if report.get("competitor_ads"):
        parts.append(f"竞品素材 {len(report['competitor_ads'])} 条")
    if report.get("pain_points"):
        parts.append(f"用户原话 {len(report['pain_points'])} 条")
    if report.get("trends"):
        parts.append(f"趋势信号 {len(report['trends'])} 条")
    return "；".join(parts) if parts else "当日无素材记录。"


CSS = r"""
:root {
  --bg: #f5f7f8;
  --ink: #172026;
  --muted: #64727a;
  --panel: #ffffff;
  --line: #dce4e8;
  --green: #0f766e;
  --green-soft: rgba(15, 118, 110, .1);
  --blue: #285f95;
  --amber: #b45309;
  --amber-soft: rgba(180, 83, 9, .1);
  --shadow: 0 18px 46px rgba(18, 30, 38, .1);
}

* { box-sizing: border-box; }

body {
  margin: 0;
  background: linear-gradient(180deg, #e9eef1 0, var(--bg) 360px);
  color: var(--ink);
  font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
  line-height: 1.55;
}

a { color: inherit; text-decoration: none; }
h1, h2, h3, p { margin: 0; }

.topbar {
  width: min(1180px, calc(100% - 40px));
  min-height: 74px;
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
}

.brand {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  font-weight: 800;
}

.brand .logo {
  width: 34px;
  height: 34px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--ink);
  color: #fff;
  font-size: 12px;
}

nav { display: flex; gap: 16px; color: var(--muted); font-size: 14px; }
nav a:hover { color: var(--ink); }

main {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto 58px;
}

.hero {
  padding: 40px 44px;
  border-radius: 10px;
  background:
    linear-gradient(135deg, rgba(15, 118, 110, .16), transparent 46%),
    var(--ink);
  color: #fff;
  box-shadow: var(--shadow);
}

.hero .eyebrow { color: #7fd1c8; }

.eyebrow {
  margin: 0 0 10px;
  color: var(--green);
  font-size: 12px;
  font-weight: 800;
  text-transform: uppercase;
}

.hero h1 {
  font-size: clamp(34px, 5vw, 52px);
  line-height: 1.08;
}

.hero p.lead {
  max-width: 640px;
  margin-top: 14px;
  color: rgba(255, 255, 255, .82);
  font-size: 16px;
}

.niche-line {
  margin-top: 18px;
  font-size: 13px;
  color: rgba(255, 255, 255, .66);
}

.setup-banner {
  margin-top: 16px;
  padding: 16px 20px;
  border: 1px dashed var(--amber);
  border-radius: 10px;
  background: var(--amber-soft);
  color: #7c4a03;
  font-size: 14px;
}

.setup-banner strong { display: block; margin-bottom: 4px; }
.setup-banner code {
  padding: 1px 6px;
  border-radius: 4px;
  background: rgba(255, 255, 255, .7);
  font-size: 13px;
}

.stats-band {
  margin: 20px 0 8px;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.stats-band div {
  padding: 20px;
  border-left: 1px solid var(--line);
}

.stats-band div:first-child { border-left: 0; }
.stats-band strong { font-size: 28px; line-height: 1; display: block; }
.stats-band span { margin-top: 6px; color: var(--muted); font-size: 13px; display: block; }

.section { margin-top: 34px; }

.section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.section-head h2 { font-size: 26px; line-height: 1.15; }
.section-head p { color: var(--muted); font-size: 13px; }

.card-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.card {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
}

.tag {
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--green-soft);
  color: var(--green);
  font-weight: 800;
}

.tag.plain {
  background: rgba(15, 23, 42, .07);
  color: var(--muted);
  font-weight: 700;
}

.card h3 { font-size: 18px; line-height: 1.32; }
.card .copy { color: var(--muted); font-size: 14px; }

.quote {
  margin: 0;
  padding: 12px 14px;
  border-left: 4px solid var(--green);
  border-radius: 0 8px 8px 0;
  background: #f4f8f8;
  color: #31424b;
  font-size: 14px;
}

.takeaway {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  font-size: 14px;
  color: #31424b;
}

.takeaway strong { color: var(--ink); }

.card-foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}

.card-foot a { color: var(--blue); font-weight: 800; white-space: nowrap; }

.trend-list { display: grid; gap: 12px; }

.trend-row {
  display: grid;
  grid-template-columns: minmax(140px, 220px) 72px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  padding: 16px 20px;
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.trend-row .kw { font-weight: 800; font-size: 16px; word-break: break-all; }

.signal {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  text-align: center;
}

.signal-up { background: var(--green-soft); color: var(--green); }
.signal-hot { background: var(--amber-soft); color: var(--amber); }
.signal-down { background: rgba(15, 23, 42, .07); color: var(--muted); }

.trend-row .evidence { color: var(--muted); font-size: 14px; }
.trend-row .suggestion { margin-top: 6px; font-size: 14px; color: #31424b; }
.trend-row a { color: var(--blue); font-weight: 800; font-size: 13px; }

.empty-block {
  grid-column: 1 / -1;
  padding: 28px;
  border: 1px dashed var(--line);
  border-radius: 10px;
  background: var(--panel);
  color: var(--muted);
  font-size: 14px;
}

.empty-block strong { color: var(--ink); display: block; margin-bottom: 6px; font-size: 16px; }
.empty-block code {
  padding: 1px 6px;
  border-radius: 4px;
  background: #eef2f4;
  font-size: 13px;
}

.topic-group { margin-top: 22px; }
.topic-group h3 { font-size: 18px; margin-bottom: 10px; }
.topic-group h3 span { color: var(--muted); font-size: 13px; font-weight: 400; margin-left: 8px; }

.status-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  vertical-align: middle;
}

.status-0 { background: var(--amber); }
.status-1 { background: var(--blue); }
.status-2 { background: var(--green); }
.status-3 { background: var(--muted); }

.archive-row {
  display: grid;
  grid-template-columns: 110px minmax(0, 1fr);
  gap: 16px;
  padding: 14px 0;
  border-top: 1px solid var(--line);
}

.archive-row .date { color: var(--green); font-weight: 800; font-size: 14px; }
.archive-row h3 { font-size: 16px; }
.archive-row p { margin-top: 6px; color: var(--muted); font-size: 14px; }
.archive-row a { display: inline-flex; margin-top: 8px; color: var(--blue); font-weight: 800; font-size: 13px; }

.panel {
  border: 1px solid var(--line);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
  padding: 26px;
}

footer {
  width: min(1180px, calc(100% - 40px));
  margin: 0 auto 36px;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 860px) {
  .card-grid { grid-template-columns: 1fr; }
  .stats-band { grid-template-columns: repeat(2, 1fr); }
  .stats-band div:nth-child(3) { border-left: 0; border-top: 1px solid var(--line); }
  .stats-band div:nth-child(4) { border-top: 1px solid var(--line); }
  .trend-row { grid-template-columns: 1fr; gap: 8px; }
}

@media (max-width: 680px) {
  .topbar, main, footer { width: min(100% - 28px, 1180px); }
  .topbar { padding: 18px 0 8px; align-items: flex-start; flex-direction: column; }
  nav { width: 100%; justify-content: space-between; }
  .hero { padding: 28px 24px; }
}
"""


def page_shell(title: str, nav: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{esc(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="./"><span class="logo">SC</span>{esc(title)}</a>
    <nav>{nav}</nav>
  </header>
  <main>
{body}
  </main>
</body>
</html>
"""


NAV_INDEX = '<a href="./">今日素材</a><a href="topics.html">选题库</a><a href="archive.html">沉淀库</a>'
NAV_TOPICS = '<a href="./">今日素材</a><a href="archive.html">沉淀库</a>'
NAV_ARCHIVE = '<a href="./">今日素材</a><a href="topics.html">选题库</a>'


def render_setup_banner(config: dict) -> str:
    if config.get("niche"):
        return ""
    return """
    <div class="setup-banner">
      <strong>框架已就绪，赛道尚未设置</strong>
      确定细分赛道后，把品类、3-5 个竞品品牌和关键词填进 <code>site.config.json</code>（可直接让 AI 助手代改），栏目就会开始为你工作。各栏目的素材格式见 <code>content/examples/materials.example.json</code>。
    </div>"""


def render_ad_card(ad: dict) -> str:
    return f"""
        <article class="card">
          <div class="card-meta">
            <span class="tag">{esc(ad.get("brand"))}</span>
            <span class="tag plain">{esc(ad.get("platform"))}</span>
          </div>
          <h3>{esc(ad.get("headline"))}</h3>
          <p class="copy">{esc(ad.get("copy"))}</p>
          <div class="takeaway"><strong>可用角度：</strong>{esc(ad.get("angle"))}</div>
          <div class="card-foot">
            <span>{esc(ad.get("noted_at"))}</span>
            <a href="{esc(ad.get("link"))}" target="_blank" rel="noreferrer">查看原素材</a>
          </div>
        </article>"""


def render_pain_card(pain: dict) -> str:
    return f"""
        <article class="card">
          <div class="card-meta"><span class="tag plain">{esc(pain.get("source"))}</span></div>
          <blockquote class="quote">{esc(pain.get("quote"))}</blockquote>
          <div class="takeaway"><strong>可改写成选题：</strong>{esc(pain.get("topic_idea"))}</div>
          <div class="card-foot">
            <span></span>
            <a href="{esc(pain.get("link"))}" target="_blank" rel="noreferrer">查看出处</a>
          </div>
        </article>"""


def render_trend_row(trend: dict) -> str:
    signal = trend.get("signal", "")
    signal_class = TREND_SIGNALS.get(signal, "signal-down")
    link_html = ""
    if trend.get("link"):
        link_html = f'<a href="{esc(trend.get("link"))}" target="_blank" rel="noreferrer">查看数据</a>'
    return f"""
        <div class="trend-row">
          <span class="kw">{esc(trend.get("keyword"))}</span>
          <span class="signal {signal_class}">{esc(signal)}</span>
          <div>
            <p class="evidence">{esc(trend.get("evidence"))}</p>
            <p class="suggestion">{esc(trend.get("suggestion"))}</p>
            {link_html}
          </div>
        </div>"""


def empty_block(title: str, hint: str) -> str:
    return f"""
        <div class="empty-block">
          <strong>{esc(title)}</strong>
          {hint}
        </div>"""


def render_index(config: dict, materials: dict, now: datetime) -> str:
    report_date = materials.get("report_date", "")
    ads = materials.get("competitor_ads") or []
    pains = materials.get("pain_points") or []
    trends = materials.get("trends") or []
    total = len(ads) + len(pains) + len(trends)
    machine_date = now.strftime("%Y-%m-%d %H:%M")

    niche = config.get("niche") or "赛道待定"
    competitors = "、".join(config.get("competitors") or []) or "待配置"
    keywords = "、".join(config.get("keywords") or []) or "待配置"

    ads_html = "\n".join(render_ad_card(ad) for ad in ads) or empty_block(
        "今日暂无竞品素材",
        "把竞品品牌名发给 AI 助手，让它从 Meta Ad Library / TikTok Creative Center 拉取正在投放的广告，填入 <code>content/materials.json</code> 的 <code>competitor_ads</code>。",
    )
    pains_html = "\n".join(render_pain_card(p) for p in pains) or empty_block(
        "今日暂无用户原话",
        "让 AI 助手去 Amazon 评论、Reddit 或竞品社媒评论区摘录用户原话，填入 <code>pain_points</code>——用户原话是最好的文案素材。",
    )
    trends_html = "\n".join(render_trend_row(t) for t in trends) or empty_block(
        "今日暂无趋势信号",
        "让 AI 助手查 Google Trends / Pinterest Trends 上品类词的热度变化，填入 <code>trends</code>。",
    )

    body = f"""
    <section class="hero">
      <p class="eyebrow">{esc(fmt_date(report_date))} · Content Material Radar</p>
      <h1>{esc(config.get("site_name", "出海内容素材雷达"))}</h1>
      <p class="lead">{esc(config.get("tagline", ""))}</p>
      <p class="niche-line">赛道：{esc(niche)} ｜ 竞品：{esc(competitors)} ｜ 关键词：{esc(keywords)}</p>
    </section>
    {render_setup_banner(config)}

    <section class="stats-band">
      <div><strong>{total}</strong><span>今日素材总数</span></div>
      <div><strong>{len(ads)}</strong><span>竞品广告素材</span></div>
      <div><strong>{len(pains)}</strong><span>用户痛点原话</span></div>
      <div><strong>{len(trends)}</strong><span>趋势信号</span></div>
    </section>

    <section class="section" id="ads">
      <div class="section-head">
        <h2>竞品广告素材</h2>
        <p>竞品正在投什么，每条附可用角度</p>
      </div>
      <div class="card-grid">{ads_html}
      </div>
    </section>

    <section class="section" id="pains">
      <div class="section-head">
        <h2>用户痛点原话</h2>
        <p>用户的真实抱怨和疑问，每条附可改写选题</p>
      </div>
      <div class="card-grid">{pains_html}
      </div>
    </section>

    <section class="section" id="trends">
      <div class="section-head">
        <h2>趋势信号</h2>
        <p>品类关键词热度变化，判断最近该做什么内容</p>
      </div>
      <div class="trend-list">{trends_html}
      </div>
    </section>

    <footer style="width:100%;margin-top:36px;">素材日期：{esc(report_date)} · 页面生成：{machine_date} Asia/Shanghai。</footer>
"""
    return page_shell(config.get("site_name", "出海内容素材雷达"), NAV_INDEX, body)


def render_topics(config: dict, topics: list[dict], now: datetime) -> str:
    groups = []
    for index, status in enumerate(TOPIC_STATUSES):
        rows = [t for t in topics if (t.get("status") or "待做") == status]
        if not rows:
            continue
        cards = []
        for topic in rows:
            meta_bits = []
            if topic.get("from"):
                meta_bits.append(f"来源：{topic['from']}")
            if topic.get("planned_date"):
                meta_bits.append(f"排期：{topic['planned_date']}")
            cards.append(f"""
        <article class="card">
          <h3>{esc(topic.get("title"))}</h3>
          <p class="copy">{esc(topic.get("notes"))}</p>
          <div class="card-foot"><span>{esc(" ｜ ".join(meta_bits))}</span></div>
        </article>""")
        groups.append(f"""
    <section class="topic-group">
      <h3><span class="status-dot status-{index}"></span>{esc(status)}<span>{len(rows)} 个</span></h3>
      <div class="card-grid">{''.join(cards)}
      </div>
    </section>""")

    if groups:
        content = "".join(groups)
    else:
        content = empty_block(
            "选题库还是空的",
            "在「今日素材」里看到可用的角度后，让 AI 助手把它登记进 <code>content/topics.json</code>：标题、来源素材、排期和状态（待做/进行中/已发布/已验证）。",
        )

    body = f"""
    <section class="hero">
      <p class="eyebrow">Topic Pipeline</p>
      <h1>选题库</h1>
      <p class="lead">素材只有变成选题并排期，才会变成发布的内容。按状态推进：待做 → 进行中 → 已发布 → 已验证。</p>
    </section>
    {content}
    <footer style="width:100%;margin-top:36px;">页面生成：{now.strftime("%Y-%m-%d %H:%M")} Asia/Shanghai。</footer>
"""
    return page_shell(f"选题库 · {config.get('site_name', '')}", NAV_TOPICS, body)


def render_archive(config: dict, history: list[dict], now: datetime) -> str:
    rows = []
    for report in history:
        count = history_entry_count(report)
        rows.append(f"""
      <div class="archive-row">
        <span class="date">{esc(report.get("report_date"))}</span>
        <div>
          <h3>{count} 条当日记录</h3>
          <p>{esc(history_entry_summary(report))}</p>
          <a href="history/{esc(report.get("report_date"))}.json" target="_blank" rel="noreferrer">查看结构化归档</a>
        </div>
      </div>""")
    rows_html = "\n".join(rows) or "<p style=\"color:var(--muted)\">历史归档将在每日素材发布后自动沉淀。</p>"

    body = f"""
    <section class="hero">
      <p class="eyebrow">Knowledge Archive</p>
      <h1>素材沉淀库</h1>
      <p class="lead">每天的素材报告自动归档，月底回看哪些角度反复出现，就是值得长期投入的内容方向。</p>
    </section>
    <section class="section">
      <div class="panel">
        <p style="color:var(--muted);margin-bottom:8px;">已沉淀 {len(history)} 期。</p>
        {rows_html}
      </div>
    </section>
    <footer style="width:100%;margin-top:36px;">页面生成：{now.strftime("%Y-%m-%d %H:%M")} Asia/Shanghai。</footer>
"""
    return page_shell(f"沉淀库 · {config.get('site_name', '')}", NAV_ARCHIVE, body)


def main() -> None:
    now = datetime.now(TIMEZONE)
    config = load_json(CONFIG_FILE, {})
    materials = load_json(MATERIALS_FILE, {})
    topics = load_json(TOPICS_FILE, {}).get("topics", [])

    check_report_freshness(materials.get("report_date", ""), now)

    PUBLIC.mkdir(exist_ok=True)
    archive_materials(materials)
    history = load_history()
    PUBLIC_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    for source in HISTORY_DIR.glob("????-??-??.json"):
        shutil.copy2(source, PUBLIC_HISTORY_DIR / source.name)

    (PUBLIC / "index.html").write_text(render_index(config, materials, now), encoding="utf-8")
    (PUBLIC / "topics.html").write_text(render_topics(config, topics, now), encoding="utf-8")
    (PUBLIC / "archive.html").write_text(render_archive(config, history, now), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    total = history_entry_count(materials)
    print(f"generated site with {total} materials and {len(topics)} topics")


if __name__ == "__main__":
    main()
