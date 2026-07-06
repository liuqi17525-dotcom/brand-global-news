import html
import json
import re
import shutil
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "public"
ASSETS = PUBLIC / "assets"
TIMEZONE = timezone(timedelta(hours=8))

CATEGORIES = [
    "平台经营",
    "内容电商",
    "DTC 独立站",
    "物流支付",
    "合规政策",
    "消费趋势",
]

QUERIES = [
    "品牌出海 跨境电商 最新",
    "中国品牌出海 DTC 独立站",
    "TikTok Shop 跨境电商 品牌",
    "Amazon Global Selling seller update",
    "cross border ecommerce China brands global",
    "DTC ecommerce global expansion logistics compliance",
]

CATEGORY_KEYWORDS = [
    ("平台经营", ["amazon", "temu", "shein", "marketplace", "seller", "平台", "卖家"]),
    ("内容电商", ["tiktok", "creator", "live", "short video", "直播", "达人", "短视频", "内容"]),
    ("DTC 独立站", ["shopify", "dtc", "独立站", "direct-to-consumer", "brand site"]),
    ("物流支付", ["logistics", "shipping", "fulfillment", "payment", "物流", "支付", "履约"]),
    ("合规政策", ["tariff", "compliance", "regulation", "privacy", "关税", "合规", "监管", "税"]),
    ("消费趋势", ["consumer", "trend", "demand", "消费者", "趋势", "需求"]),
]

CATEGORY_COVERS = {
    "平台经营": "cover-platform.png",
    "内容电商": "cover-content.png",
    "DTC 独立站": "cover-dtc.png",
    "品牌出海": "cover-global.png",
    "物流支付": "cover-logistics.png",
    "合规政策": "cover-compliance.png",
    "消费趋势": "cover-consumer.png",
}


@dataclass
class Item:
    title: str
    link: str
    source: str
    published: str
    summary: str
    category: str
    heat: int
    fallback: bool = False


def fetch_url(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 brand-global-news/4.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_link(link: str) -> str:
    if "news.google.com" not in link:
        return link
    params = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    return params.get("url", [link])[0]


def source_from_item(item: ET.Element) -> str:
    source = item.findtext("source")
    if source:
        return strip_tags(source)
    link = item.findtext("link") or ""
    return urllib.parse.urlparse(link).netloc.replace("www.", "") or "资讯源"


def parse_date(value: str) -> datetime:
    try:
        return parsedate_to_datetime(value).astimezone(TIMEZONE)
    except Exception:
        return datetime.now(TIMEZONE)


def category_for(title: str, summary: str) -> str:
    text = f"{title} {summary}".lower()
    for category, words in CATEGORY_KEYWORDS:
        if any(word.lower() in text for word in words):
            return category
    return "品牌出海"


def heat_for(title: str, summary: str, index: int) -> int:
    text = f"{title} {summary}".lower()
    score = 68 + max(0, 18 - index * 2)
    for _, words in CATEGORY_KEYWORDS:
        score += sum(2 for word in words if word.lower() in text)
    return min(score, 96)


def insight_for(category: str) -> str:
    mapping = {
        "平台经营": "用平台验证市场和价格带，同时把评价、品牌资产和用户反馈沉淀下来。",
        "内容电商": "把达人、素材、商品页和库存联动起来，避免只有流量没有稳定转化。",
        "DTC 独立站": "关注复购、支付体验和一方数据，不要只用广告 ROAS 判断成败。",
        "品牌出海": "判断品牌资产、市场定位和渠道组合是否能支撑长期增长。",
        "物流支付": "核心市场优先保障履约确定性，物流体验会直接影响评价和复购。",
        "合规政策": "把税务、认证、标签和隐私要求前置到选品与上市流程里。",
        "消费趋势": "从搜索、评论和社媒语境里捕捉本地需求，不要直接复制国内卖点。",
    }
    return mapping.get(category, "判断品牌资产、市场定位和渠道组合是否能支撑长期增长。")


def fetch_google_news(query: str) -> list[Item]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    data = fetch_url(url)
    root = ET.fromstring(data)
    items: list[Item] = []
    for index, node in enumerate(root.findall("./channel/item")[:8]):
        title = strip_tags(node.findtext("title") or "")
        link = normalize_link(strip_tags(node.findtext("link") or ""))
        summary = strip_tags(node.findtext("description") or "")
        published_dt = parse_date(node.findtext("pubDate") or "")
        source = source_from_item(node)
        category = category_for(title, summary)
        items.append(
            Item(
                title=title,
                link=link,
                source=source,
                published=published_dt.strftime("%Y-%m-%d"),
                summary=summary[:220],
                category=category,
                heat=heat_for(title, summary, index),
                fallback=False,
            )
        )
    return items


def collect_items() -> list[Item]:
    seen: set[str] = set()
    collected: list[Item] = []
    for query in QUERIES:
        try:
            for item in fetch_google_news(query):
                key = re.sub(r"\W+", "", item.title.lower())[:90]
                if key and key not in seen:
                    seen.add(key)
                    collected.append(item)
        except Exception as exc:
            print(f"warn: failed query {query}: {exc}", file=sys.stderr)
    collected.sort(key=lambda item: (item.heat, item.published), reverse=True)
    return collected[:8]


def fallback_items(today: str) -> list[Item]:
    seeds = [
        ("平台全球化工具继续降低多市场经营门槛", "https://sell.amazon.com/global-selling", "Amazon Global Selling", "平台经营"),
        ("内容电商把种草、成交和履约压缩到同一链路", "https://seller.tiktokglobalshop.com/university", "TikTok Shop Academy", "内容电商"),
        ("独立站经营重点转向复购、一方数据和本地化支付", "https://www.shopify.com/research/commerce-trends", "Shopify", "DTC 独立站"),
        ("品牌出海从铺渠道转向经营长期信任资产", "https://www.shopify.com/research/commerce-trends", "Shopify", "品牌出海"),
        ("履约体验正在成为海外消费者评价品牌的关键", "https://www.dhl.com/global-en/home/insights-and-innovation.html", "DHL Insights", "物流支付"),
        ("成熟市场的关税、数据和产品安全要求继续抬高门槛", "https://trade.ec.europa.eu/access-to-markets/en/home", "EU Access2Markets", "合规政策"),
    ]
    return [
        Item(
            title=title,
            link=link,
            source=source,
            published=today,
            summary="自动资讯源暂时不可用，先展示稳定观察项。每日任务会在 GitHub 云端重新抓取最新来源。",
            category=category,
            heat=92 - index * 3,
            fallback=True,
        )
        for index, (title, link, source, category) in enumerate(seeds)
    ]


def ensure_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    for filename in [
        "global-commerce-hero.png",
        "hotspots-data-cover.png",
        *CATEGORY_COVERS.values(),
    ]:
        source = ROOT / "assets" / filename
        if source.exists():
            shutil.copy2(source, ASSETS / filename)


def fmt_date(now: datetime) -> str:
    return f"{now.year}年{now.month}月{now.day}日"


def summary_mode(now: datetime) -> tuple[str, str]:
    if now.month == 12 and now.day == 31:
        return "年终总结", f"{now.year} 年品牌出海年度复盘"
    if (now.month, now.day) in {(3, 31), (6, 30), (9, 30)}:
        quarter = (now.month - 1) // 3 + 1
        return "季度总结", f"{now.year} Q{quarter} 品牌出海季度复盘"
    return "今日分析", "今天的资讯说明了什么"


def category_counts(items: list[Item]) -> dict[str, int]:
    counts = {category: 0 for category in CATEGORIES}
    for item in items:
        counts[item.category] = counts.get(item.category, 0) + 1
    return counts


def analysis_points(items: list[Item], now: datetime) -> list[str]:
    counts = category_counts(items)
    ordered = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    top = ordered[0][0] if ordered else "品牌出海"
    second = ordered[1][0] if len(ordered) > 1 else "内容与履约"
    mode, _ = summary_mode(now)
    prefix = "本期" if mode != "今日分析" else "今天"
    return [
        f"{prefix}最集中的信号来自「{top}」，说明出海经营的核心注意力正在向这一侧倾斜。",
        f"「{second}」也值得跟进，它往往决定流量能不能转成稳定订单和可复购用户。",
        "建议把资讯拆成三个动作：调整选品假设、验证渠道效率、检查履约与合规成本。",
    ]


def cover_for(category: str) -> str:
    return CATEGORY_COVERS.get(category, CATEGORY_COVERS["品牌出海"])


def render_modules(items: list[Item]) -> str:
    counts = category_counts(items)
    cards = []
    for category in CATEGORIES:
        cards.append(
            f"""
            <article class="module-card">
              <img src="assets/{cover_for(category)}" alt="{html.escape(category)}封面" />
              <div>
                <span>{counts.get(category, 0)} 条</span>
                <h3>{html.escape(category)}</h3>
                <p>{html.escape(insight_for(category))}</p>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def render_cards(items: list[Item]) -> str:
    cards = []
    for index, item in enumerate(items, start=1):
        link_text = "查看来源详情" if item.fallback else "查看原文"
        cards.append(
            f"""
            <article class="news-card">
              <img src="assets/{cover_for(item.category)}" alt="资讯预览图" />
              <div class="card-body">
                <div class="card-meta">
                  <span>{index:02d}</span>
                  <span>热度 {item.heat}</span>
                </div>
                <h3>{html.escape(item.title)}</h3>
                <p>{html.escape(item.summary or "暂无摘要，请点击来源查看详情。")}</p>
                <div class="insight">启示：{html.escape(insight_for(item.category))}</div>
                <div class="card-foot">
                  <span>{html.escape(item.source)} · {html.escape(item.published)}</span>
                  <a href="{html.escape(item.link)}" target="_blank" rel="noreferrer">{link_text}</a>
                </div>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def render_analysis_items(items: list[Item]) -> str:
    rows = []
    for index, item in enumerate(items, start=1):
        rows.append(
            f"""
            <article class="analysis-source">
              <span>{index:02d}</span>
              <div>
                <h3>{html.escape(item.title)}</h3>
                <p>{html.escape(item.summary or "暂无摘要，请点击来源查看原文。")}</p>
                <a href="{html.escape(item.link)}" target="_blank" rel="noreferrer">{html.escape(item.source)} · 查看原文</a>
              </div>
            </article>
            """
        )
    return "\n".join(rows)


def render_analysis_html(items: list[Item], now: datetime) -> str:
    today = fmt_date(now)
    machine_date = now.strftime("%Y-%m-%d %H:%M")
    mode, analysis_title = summary_mode(now)
    counts = category_counts(items)
    ordered = sorted(counts.items(), key=lambda pair: pair[1], reverse=True)
    top = ordered[0][0] if ordered else "品牌出海"
    second = ordered[1][0] if len(ordered) > 1 else "内容电商"
    source_count = len({item.source for item in items})

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{mode} · 品牌出海热点速递</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="./"><span>BG</span>品牌出海热点速递</a>
    <nav>
      <a href="./">首页</a>
      <a href="#summary">综合判断</a>
    </nav>
  </header>

  <main class="analysis-page">
    <section class="analysis-hero">
      <p class="eyebrow">{today} · {mode}</p>
      <h1>{analysis_title}</h1>
      <p>这不是资讯复述，而是把今天抓到的 {len(items)} 条热点和 {source_count} 个来源合在一起，判断它们共同指向的出海经营变化。</p>
    </section>

    <section class="analysis-long" id="summary">
      <h2>综合判断</h2>
      <p>今天的资讯重心集中在「{html.escape(top)}」和「{html.escape(second)}」。这说明品牌出海已经不是单纯找一个新渠道、投一波广告的问题，而是要同时处理平台效率、内容转化、履约体验和本地合规之间的关系。</p>
      <p>如果把这些信息放在经营视角里看，最重要的变化是：品牌需要从“单点爆发”转向“系统经营”。平台能带来早期确定性，内容电商能带来发现和转化，独立站能沉淀用户资产，但这些链路只有在履约和合规跟得上的情况下，才会形成稳定增长。</p>
      <p>今天更值得关注的不是某一条新闻本身，而是它们共同指向的经营压力：流量越来越碎，平台规则越来越细，消费者对交付和信任的要求越来越高。品牌要做的不是追每一个热点，而是判断哪些变化会影响自己的选品、价格、内容和供应链。</p>
      <p>对你来说，比较实际的读法是：先看今天哪些信息会改变“增长假设”。如果热点主要集中在平台经营，说明短期要关注规则、流量入口和店铺效率；如果集中在内容电商，说明素材、达人和商品页承接会更重要；如果物流、支付和合规信号变多，就意味着成本和风险可能比流量机会更先影响利润。</p>
      <p>所以这份日报真正要回答的不是“今天发生了什么”，而是“今天哪些变化可能让原来的出海打法失效”。当多个来源同时指向同一个方向时，它就不只是新闻，而是需要进入你的选品、市场和渠道判断里的经营信号。</p>
    </section>
  </main>

  <footer>
    最后更新：{machine_date} Asia/Shanghai。季度最后一天自动切换为季度总结；12月31日自动切换为年终总结。
  </footer>
</body>
</html>
"""


def render_html(items: list[Item], now: datetime) -> str:
    today = fmt_date(now)
    machine_date = now.strftime("%Y-%m-%d %H:%M")
    source_count = len({item.source for item in items})
    mode, analysis_title = summary_mode(now)
    top_title = items[0].title if items else "今日暂无可用资讯"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>品牌出海热点速递</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="./"><span>BG</span>品牌出海热点速递</a>
    <nav>
      <a href="#modules">模块</a>
      <a href="analysis.html">分析</a>
      <a href="#news">热点</a>
    </nav>
  </header>

  <main>
    <section class="hero">
      <img src="assets/global-commerce-hero.png" alt="出海热点封面" />
      <div class="hero-copy">
        <p class="eyebrow">{today} · Global Brand Intelligence</p>
        <h1>出海热点</h1>
        <p>今日值得知道的品牌出海资讯与综合判断。</p>
        <div class="hero-actions">
          <a href="analysis.html">查看综合分析</a>
        </div>
      </div>
    </section>

    <section class="data-band">
      <img src="assets/hotspots-data-cover.png" alt="8条热点数据封面" />
      <div class="data-copy">
        <p class="eyebrow">Daily Signal</p>
        <h2>{len(items)} 条热点，{source_count} 个来源</h2>
        <p>用最少数字概括今天的信息密度，帮助你先判断这期日报的观察价值。</p>
      </div>
      <div class="data-stats">
        <div><strong>{len(items)}</strong><span>热点</span></div>
        <div><strong>{source_count}</strong><span>来源</span></div>
      </div>
    </section>

    <section class="modules" id="modules">
      <div class="section-head">
        <p class="eyebrow">Fixed Modules</p>
        <h2>固定观察模块</h2>
      </div>
      <div class="module-grid">
        {render_modules(items)}
      </div>
    </section>

    <section class="news-section" id="news">
      <div class="section-head">
        <p class="eyebrow">News Feed</p>
        <h2>热点卡片</h2>
      </div>
      <div class="news-grid">
        {render_cards(items)}
      </div>
    </section>
  </main>

  <footer>
    最后更新：{machine_date} Asia/Shanghai。
  </footer>
</body>
</html>
"""


CSS = r"""
:root {
  --bg: #f5f7f8;
  --ink: #172026;
  --muted: #64727a;
  --panel: #ffffff;
  --line: #dce4e8;
  --green: #0f766e;
  --blue: #285f95;
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

.topbar {
  width: min(1240px, calc(100% - 40px));
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

.brand span {
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

main {
  width: min(1240px, calc(100% - 40px));
  margin: 0 auto 58px;
}

.hero {
  min-height: 560px;
  position: relative;
  display: flex;
  align-items: flex-end;
  border: 1px solid rgba(220, 228, 232, .92);
  border-radius: 10px;
  box-shadow: var(--shadow);
  overflow: hidden;
  background: #111b22;
}

.hero > img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.hero::after {
  content: "";
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(8, 16, 20, .88), rgba(8, 16, 20, .42) 48%, rgba(8, 16, 20, .76)),
    linear-gradient(0deg, rgba(8, 16, 20, .82), transparent 56%);
}

.data-band,
.module-card,
.analysis-panel,
.news-card {
  border: 1px solid rgba(220, 228, 232, .92);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
  overflow: hidden;
}

.hero-copy {
  width: min(760px, calc(100% - 48px));
  padding: 0 0 44px 44px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  position: relative;
  z-index: 1;
  color: #fff;
}

.hero-copy::after {
  content: none;
}

.eyebrow {
  margin: 0 0 12px;
  color: var(--green);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0;
  text-transform: uppercase;
}

h1, h2, h3, p { margin: 0; }

h1 {
  max-width: 720px;
  font-size: clamp(48px, 7vw, 86px);
  line-height: .98;
  letter-spacing: 0;
  position: relative;
  z-index: 1;
}

.hero-copy p:not(.eyebrow) {
  max-width: 720px;
  margin-top: 18px;
  color: rgba(255,255,255,.82);
  font-size: 18px;
  position: relative;
  z-index: 1;
}

.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 28px;
  position: relative;
  z-index: 1;
}

.hero-actions a {
  padding: 10px 14px;
  border-radius: 8px;
  background: #fff;
  color: var(--ink);
  font-weight: 800;
  font-size: 14px;
}

.hero-actions a + a {
  background: rgba(255,255,255,.12);
  color: #fff;
  border: 1px solid rgba(255,255,255,.24);
}

.data-band > img,
.module-card img,
.news-card img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.data-band {
  min-height: 190px;
  display: grid;
  grid-template-columns: 280px minmax(0, 1fr) 240px;
  gap: 0;
  margin: 20px 0;
}

.data-band > img { min-height: 190px; filter: saturate(.9) contrast(.95); }

.data-copy {
  padding: 24px;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.data-copy h2,
.section-head h2,
.analysis-panel h2 {
  font-size: 28px;
  line-height: 1.15;
}

.data-copy p:not(.eyebrow) {
  margin-top: 10px;
  color: var(--muted);
}

.data-stats {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  border-left: 1px solid var(--line);
}

.data-stats div {
  padding: 22px 18px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  border-left: 1px solid var(--line);
}

.data-stats strong { font-size: 30px; line-height: 1; }
.data-stats span { margin-top: 8px; color: var(--muted); font-size: 13px; }

.section-head { margin: 28px 0 14px; }

.module-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.module-card {
  min-height: 220px;
  display: grid;
  grid-template-rows: 110px 1fr;
}

.module-card img { filter: brightness(.78) saturate(.9); }

.module-card div { padding: 16px; }
.module-card span { color: var(--green); font-size: 12px; font-weight: 800; }
.module-card h3 { margin-top: 6px; font-size: 20px; }
.module-card p { margin-top: 8px; color: var(--muted); font-size: 13px; }

.analysis-panel {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 24px;
  padding: 24px;
  margin: 24px 0;
  border-left: 6px solid var(--green);
}

.analysis-panel ol { margin: 0; padding-left: 22px; color: var(--muted); }
.analysis-panel li + li { margin-top: 10px; }

.analysis-teaser {
  color: var(--muted);
}

.analysis-teaser a {
  display: inline-flex;
  margin-top: 14px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--ink);
  color: #fff;
  font-weight: 800;
  font-size: 14px;
}

.analysis-page {
  max-width: 980px;
}

.analysis-hero,
.analysis-long {
  border: 1px solid rgba(220, 228, 232, .92);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.analysis-hero {
  padding: 42px;
  margin-bottom: 20px;
  background:
    linear-gradient(135deg, rgba(15, 118, 110, .12), transparent 42%),
    #fff;
}

.analysis-hero h1 {
  max-width: 780px;
}

.analysis-hero p:not(.eyebrow) {
  max-width: 760px;
  margin-top: 18px;
  color: var(--muted);
  font-size: 18px;
}

.analysis-long {
  padding: 28px;
  margin-bottom: 18px;
}

.analysis-long h2 {
  font-size: 28px;
  line-height: 1.15;
  margin-bottom: 14px;
}

.analysis-long p {
  color: var(--muted);
  font-size: 16px;
}

.analysis-long p + p {
  margin-top: 14px;
}

.analysis-long ol {
  margin: 0;
  padding-left: 22px;
  color: var(--muted);
}

.analysis-long li + li {
  margin-top: 10px;
}

.analysis-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.analysis-grid div {
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  background: #f9fbfb;
}

.analysis-grid strong {
  display: block;
  margin-bottom: 6px;
}

.analysis-grid p {
  font-size: 14px;
}

.analysis-sources {
  display: grid;
  gap: 12px;
}

.analysis-source {
  display: grid;
  grid-template-columns: 44px minmax(0, 1fr);
  gap: 14px;
  padding: 14px 0;
  border-top: 1px solid var(--line);
}

.analysis-source span {
  color: var(--green);
  font-weight: 900;
}

.analysis-source h3 {
  font-size: 18px;
  line-height: 1.28;
}

.analysis-source p {
  margin-top: 8px;
  color: var(--muted);
  font-size: 14px;
}

.analysis-source a {
  display: inline-flex;
  margin-top: 10px;
  color: var(--blue);
  font-weight: 800;
  font-size: 13px;
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.news-card {
  min-height: 388px;
  display: grid;
  grid-template-rows: 138px 1fr;
}

.news-card > img { filter: brightness(.78) saturate(.92); }

.card-body {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.card-meta,
.card-foot {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  color: var(--muted);
  font-size: 12px;
}

.news-card h3 { font-size: 19px; line-height: 1.28; }
.news-card p { color: var(--muted); font-size: 14px; }

.insight {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  color: #31424b;
  font-size: 14px;
}

.card-foot a { color: var(--blue); font-weight: 800; white-space: nowrap; }

footer {
  width: min(1240px, calc(100% - 40px));
  margin: 0 auto 36px;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 1020px) {
  .hero,
  .data-band,
  .analysis-panel { grid-template-columns: 1fr; }
  .data-stats { border-left: 0; border-top: 1px solid var(--line); }
  .module-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 680px) {
  .topbar,
  main,
  footer { width: min(100% - 28px, 1240px); }
  .topbar { padding: 18px 0 8px; align-items: flex-start; flex-direction: column; }
  nav { width: 100%; justify-content: space-between; }
  .hero-copy { padding: 24px; min-height: 420px; }
  h1 { font-size: 42px; }
  .data-stats,
  .module-grid,
  .news-grid,
  .analysis-grid { grid-template-columns: 1fr; }
}
"""


def main() -> None:
    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    items = collect_items()
    if not items:
        items = fallback_items(today)

    PUBLIC.mkdir(exist_ok=True)
    ensure_assets()
    (PUBLIC / "index.html").write_text(render_html(items, now), encoding="utf-8")
    (PUBLIC / "analysis.html").write_text(render_analysis_html(items, now), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    (PUBLIC / "latest.json").write_text(
        json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"generated {PUBLIC / 'index.html'} with {len(items)} items")


if __name__ == "__main__":
    main()
