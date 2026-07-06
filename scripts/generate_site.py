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

COVER_CLASS = {
    "平台经营": "cover-platform",
    "内容电商": "cover-content",
    "DTC 独立站": "cover-dtc",
    "物流支付": "cover-logistics",
    "合规政策": "cover-compliance",
    "消费趋势": "cover-consumer",
    "品牌出海": "cover-global",
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


def fetch_url(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 brand-global-news/3.0",
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
        "物流支付": "核心市场优先保障履约确定性，物流体验会直接影响评价和复购。",
        "合规政策": "把税务、认证、标签和隐私要求前置到选品与上市流程里。",
        "消费趋势": "从搜索、评论和社媒语境里捕捉本地需求，不要直接复制国内卖点。",
    }
    return mapping.get(category, "判断这条信息是否会影响选品、渠道、内容或履约优先级。")


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
        ("内容电商把种草、成交和履约压缩到同一链路", "https://seller.tiktok.com/", "TikTok Shop", "内容电商"),
        ("独立站经营重点转向复购、一方数据和本地化支付", "https://www.shopify.com/research/commerce-trends", "Shopify", "DTC 独立站"),
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
            heat=90 - index * 3,
        )
        for index, (title, link, source, category) in enumerate(seeds)
    ]


def ensure_assets() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    source = ROOT / "assets" / "global-commerce-hero.png"
    target = ASSETS / "global-commerce-hero.png"
    if source.exists():
        shutil.copy2(source, target)


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
    counts: dict[str, int] = {}
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


def render_section_covers(categories: list[str]) -> str:
    blocks = []
    labels = categories or ["平台经营", "内容电商", "DTC 独立站", "物流支付", "合规政策", "消费趋势"]
    for category in labels[:6]:
        cover = COVER_CLASS.get(category, "cover-global")
        blocks.append(
            f"""
            <button class="section-cover {cover}" data-filter="{html.escape(category)}" type="button">
              <span>{html.escape(category)}</span>
              <small>{html.escape(insight_for(category))}</small>
            </button>
            """
        )
    return "\n".join(blocks)


def render_filter_buttons(categories: list[str]) -> str:
    buttons = ['<button class="filter is-active" data-filter="all" type="button">全部</button>']
    for category in categories:
        buttons.append(
            f'<button class="filter" data-filter="{html.escape(category)}" type="button">{html.escape(category)}</button>'
        )
    return "\n".join(buttons)


def render_cards(items: list[Item]) -> str:
    cards = []
    for index, item in enumerate(items, start=1):
        cover = COVER_CLASS.get(item.category, "cover-global")
        cards.append(
            f"""
            <article class="news-card" data-category="{html.escape(item.category)}">
              <div class="card-cover {cover}">
                <span>{index:02d}</span>
              </div>
              <div class="card-body">
                <div class="card-meta">
                  <span class="tag">{html.escape(item.category)}</span>
                  <span>热度 {item.heat}</span>
                </div>
                <h3>{html.escape(item.title)}</h3>
                <p>{html.escape(item.summary or "暂无摘要，请点击来源查看原文。")}</p>
                <div class="insight">启示：{html.escape(insight_for(item.category))}</div>
                <div class="card-foot">
                  <span>{html.escape(item.source)} · {html.escape(item.published)}</span>
                  <a href="{html.escape(item.link)}" target="_blank" rel="noreferrer">查看原文</a>
                </div>
              </div>
            </article>
            """
        )
    return "\n".join(cards)


def render_html(items: list[Item], now: datetime) -> str:
    today = fmt_date(now)
    machine_date = now.strftime("%Y-%m-%d %H:%M")
    categories = sorted({item.category for item in items})
    source_count = len({item.source for item in items})
    mode, analysis_title = summary_mode(now)
    points = analysis_points(items, now)
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
      <a href="#covers">版块</a>
      <a href="#analysis">分析</a>
      <a href="#news">热点</a>
    </nav>
  </header>

  <main>
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">{today} · Global Brand Intelligence</p>
        <h1>今天的出海热点，先看这几条信号</h1>
        <p>{html.escape(top_title)}</p>
        <div class="hero-actions">
          <a href="#news">查看热点</a>
          <a href="#analysis">阅读分析</a>
        </div>
      </div>
      <div class="hero-media">
        <img src="assets/global-commerce-hero.png" alt="品牌出海全球商业封面" />
        <div>
          <strong>{len(items)}</strong>
          <span>条热点 · {source_count} 个来源</span>
        </div>
      </div>
    </section>

    <section class="section-covers" id="covers" aria-label="资讯版块">
      {render_section_covers(categories)}
    </section>

    <section class="analysis-panel" id="analysis">
      <div>
        <p class="eyebrow">{mode}</p>
        <h2>{analysis_title}</h2>
      </div>
      <ol>
        {''.join(f'<li>{html.escape(point)}</li>' for point in points)}
      </ol>
    </section>

    <section class="news-section" id="news">
      <div class="section-head">
        <div>
          <p class="eyebrow">News Feed</p>
          <h2>热点卡片</h2>
        </div>
        <div class="filters" aria-label="筛选热点">
          {render_filter_buttons(categories)}
        </div>
      </div>
      <div class="news-grid">
        {render_cards(items)}
      </div>
    </section>
  </main>

  <footer>
    最后更新：{machine_date} Asia/Shanghai。每日为今日分析；季度最后一天自动切换为季度总结；12月31日自动切换为年终总结。
  </footer>

  <script>
    const buttons = document.querySelectorAll("[data-filter]");
    const filters = document.querySelectorAll(".filter");
    const cards = document.querySelectorAll(".news-card");

    function applyFilter(value) {{
      filters.forEach((button) => button.classList.toggle("is-active", button.dataset.filter === value));
      cards.forEach((card) => {{
        const show = value === "all" || card.dataset.category === value;
        card.hidden = !show;
      }});
      document.querySelector("#news").scrollIntoView({{ behavior: "smooth", block: "start" }});
    }}

    buttons.forEach((button) => {{
      button.addEventListener("click", () => applyFilter(button.dataset.filter));
    }});
  </script>
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
  --gold: #b87922;
  --red: #be4444;
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
  height: 74px;
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

nav {
  display: flex;
  gap: 16px;
  color: var(--muted);
  font-size: 14px;
}

main {
  width: min(1240px, calc(100% - 40px));
  margin: 0 auto 58px;
}

.hero {
  min-height: 460px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 430px;
  gap: 20px;
}

.hero-copy,
.hero-media,
.section-cover,
.analysis-panel,
.news-card {
  border: 1px solid rgba(220, 228, 232, .92);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow);
}

.hero-copy {
  padding: 42px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  background:
    linear-gradient(135deg, rgba(15, 118, 110, .12), transparent 40%),
    linear-gradient(90deg, #fff, #f8fbfc);
  overflow: hidden;
  position: relative;
}

.hero-copy::after {
  content: "";
  position: absolute;
  right: 36px;
  top: 36px;
  width: 260px;
  height: 260px;
  border-radius: 50%;
  border: 1px solid rgba(40, 95, 149, .22);
  box-shadow: inset 0 0 0 34px rgba(15, 118, 110, .05), inset 0 0 0 88px rgba(184, 121, 34, .05);
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
  font-size: clamp(46px, 7vw, 82px);
  line-height: .98;
  letter-spacing: 0;
  position: relative;
  z-index: 1;
}

.hero-copy p:not(.eyebrow) {
  max-width: 720px;
  margin-top: 18px;
  color: var(--muted);
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
  background: var(--ink);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
}

.hero-actions a + a {
  background: #eaf2f1;
  color: var(--green);
}

.hero-media {
  min-height: 460px;
  overflow: hidden;
  position: relative;
  background: #111b22;
}

.hero-media img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  opacity: .52;
  filter: saturate(.92) contrast(.98);
}

.hero-media::after {
  content: "";
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, transparent 20%, rgba(8, 16, 20, .88));
}

.hero-media div {
  position: absolute;
  left: 24px;
  right: 24px;
  bottom: 24px;
  color: #fff;
  z-index: 1;
}

.hero-media strong {
  display: block;
  font-size: 64px;
  line-height: 1;
}

.hero-media span {
  color: rgba(255,255,255,.78);
}

.section-covers {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 20px 0;
}

.section-cover {
  min-height: 148px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  align-items: flex-start;
  text-align: left;
  cursor: pointer;
  color: #fff;
  overflow: hidden;
  position: relative;
  border: 0;
  font: inherit;
}

.section-cover::before,
.card-cover::before {
  content: "";
  position: absolute;
  inset: 0;
  background:
    radial-gradient(circle at 18% 22%, rgba(255,255,255,.35), transparent 20%),
    linear-gradient(135deg, rgba(255,255,255,.16), transparent 46%);
}

.section-cover span {
  font-size: 22px;
  font-weight: 800;
  position: relative;
}

.section-cover small {
  margin-top: 8px;
  color: rgba(255,255,255,.78);
  position: relative;
}

.cover-platform { background: linear-gradient(135deg, #0f766e, #123f4a); }
.cover-content { background: linear-gradient(135deg, #9d3f57, #3f2f76); }
.cover-dtc { background: linear-gradient(135deg, #285f95, #16385c); }
.cover-logistics { background: linear-gradient(135deg, #b87922, #4b4f36); }
.cover-compliance { background: linear-gradient(135deg, #243241, #59616b); }
.cover-consumer { background: linear-gradient(135deg, #4c7a53, #1e4f61); }
.cover-global { background: linear-gradient(135deg, #172026, #0f766e); }

.analysis-panel {
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 24px;
  padding: 24px;
  margin-bottom: 24px;
  border-left: 6px solid var(--green);
}

.analysis-panel h2,
.section-head h2 {
  font-size: 28px;
  line-height: 1.15;
}

.analysis-panel ol {
  margin: 0;
  padding-left: 22px;
  color: var(--muted);
}

.analysis-panel li + li { margin-top: 10px; }

.section-head {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: end;
  margin-bottom: 14px;
}

.filters {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}

.filter {
  border: 1px solid var(--line);
  background: #fff;
  color: var(--muted);
  border-radius: 999px;
  padding: 8px 12px;
  cursor: pointer;
  font: inherit;
  font-size: 13px;
}

.filter.is-active {
  color: #fff;
  background: var(--ink);
  border-color: var(--ink);
}

.news-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.news-card {
  min-height: 360px;
  overflow: hidden;
  display: grid;
  grid-template-rows: 118px 1fr;
}

.card-cover {
  position: relative;
  display: flex;
  align-items: flex-end;
  padding: 16px;
  color: #fff;
  overflow: hidden;
}

.card-cover span {
  position: relative;
  z-index: 1;
  font-size: 28px;
  font-weight: 900;
}

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

.tag {
  color: var(--green);
  font-weight: 800;
}

.news-card h3 {
  font-size: 19px;
  line-height: 1.28;
}

.news-card p {
  color: var(--muted);
  font-size: 14px;
}

.insight {
  margin-top: auto;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  color: #31424b;
  font-size: 14px;
}

.card-foot a {
  color: var(--blue);
  font-weight: 800;
  white-space: nowrap;
}

footer {
  width: min(1240px, calc(100% - 40px));
  margin: 0 auto 36px;
  color: var(--muted);
  font-size: 13px;
}

@media (max-width: 960px) {
  .hero,
  .analysis-panel {
    grid-template-columns: 1fr;
  }

  .hero-media {
    min-height: 280px;
  }

  .section-covers,
  .news-grid {
    grid-template-columns: 1fr 1fr;
  }
}

@media (max-width: 640px) {
  .topbar,
  main,
  footer {
    width: min(100% - 28px, 1240px);
  }

  .topbar {
    height: auto;
    padding: 18px 0 8px;
    align-items: flex-start;
    flex-direction: column;
  }

  nav {
    width: 100%;
    justify-content: space-between;
  }

  .hero-copy {
    padding: 24px;
    min-height: 420px;
  }

  h1 {
    font-size: 42px;
  }

  .section-covers,
  .news-grid {
    grid-template-columns: 1fr;
  }

  .section-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .filters {
    justify-content: flex-start;
  }
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
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    (PUBLIC / "latest.json").write_text(
        json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"generated {PUBLIC / 'index.html'} with {len(items)} items")


if __name__ == "__main__":
    main()
