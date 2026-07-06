import html
import json
import re
import shutil
import sys
import textwrap
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
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
    ("内容电商", ["tiktok", "short video", "creator", "live", "直播", "达人", "短视频", "内容"]),
    ("平台经营", ["amazon", "temu", "shein", "shop", "marketplace", "平台", "卖家"]),
    ("DTC 独立站", ["shopify", "dtc", "独立站", "direct-to-consumer", "brand site"]),
    ("物流支付", ["logistics", "shipping", "fulfillment", "payment", "物流", "支付", "履约"]),
    ("合规政策", ["tariff", "compliance", "regulation", "privacy", "关税", "合规", "监管", "税"]),
    ("消费趋势", ["consumer", "trend", "demand", "消费者", "趋势", "需求"]),
]


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
            "User-Agent": "Mozilla/5.0 brand-global-news/1.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def source_from_item(item: ET.Element) -> str:
    source = item.findtext("source")
    if source:
        return strip_tags(source)
    link = item.findtext("link") or ""
    host = urllib.parse.urlparse(link).netloc.replace("www.", "")
    return host or "资讯源"


def normalize_link(link: str) -> str:
    if "news.google.com" not in link:
        return link
    parsed = urllib.parse.urlparse(link)
    params = urllib.parse.parse_qs(parsed.query)
    return params.get("url", [link])[0]


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
    score = 70
    score += max(0, 14 - index * 2)
    for _, words in CATEGORY_KEYWORDS:
        score += sum(2 for word in words if word.lower() in text)
    return min(score, 96)


def insight_for(item: Item) -> str:
    mapping = {
        "内容电商": "把达人、素材、商品页和库存联动起来，避免只有流量没有稳定转化。",
        "平台经营": "用平台验证市场和价格带，同时把品牌资产、评价和数据沉淀下来。",
        "DTC 独立站": "关注复购、支付体验和一方数据，别只用广告 ROAS 判断成败。",
        "物流支付": "核心市场优先保障履约确定性，物流体验会直接影响评价和复购。",
        "合规政策": "把税务、认证、标签和隐私要求前置到选品与上市流程里。",
        "消费趋势": "从搜索、评论和社媒语境里捕捉本地需求，不要直接复制国内卖点。",
    }
    return mapping.get(item.category, "判断这条信息是否会影响选品、渠道、内容或履约优先级。")


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
                if not key or key in seen:
                    continue
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
            summary="自动资讯源暂时不可用，先展示稳定观察项。上线后每日任务会重新抓取最新来源。",
            category=category,
            heat=86 - index * 3,
        )
        for index, (title, link, source, category) in enumerate(seeds)
    ]


def render_cards(items: list[Item]) -> str:
    cards = []
    for item in items:
        cards.append(
            f"""
            <article class="card">
              <div class="tag-row">
                <span class="tag">{html.escape(item.category)}</span>
                <span class="heat">热度 {item.heat}</span>
              </div>
              <h3>{html.escape(item.title)}</h3>
              <p>{html.escape(item.summary or "暂无摘要，请点击来源查看原文。")}</p>
              <div class="meta">{html.escape(item.source)} · {html.escape(item.published)}</div>
              <div class="insight">启示：{html.escape(insight_for(item))}</div>
              <a class="source" href="{html.escape(item.link)}" target="_blank" rel="noreferrer">查看来源</a>
            </article>
            """
        )
    return "\n".join(cards)


def render_html(items: list[Item], now: datetime) -> str:
    today = now.strftime("%Y年%-m月%-d日") if sys.platform != "win32" else f"{now.year}年{now.month}月{now.day}日"
    machine_date = now.strftime("%Y-%m-%d %H:%M")
    categories = sorted({item.category for item in items})
    category_html = "".join(f"<span>{html.escape(category)}</span>" for category in categories)
    cards_html = render_cards(items)
    source_count = len({item.source for item in items})

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>品牌出海热点速递</title>
  <style>
{CSS}
  </style>
</head>
<body>
  <section class="hero">
    <img src="assets/global-commerce-hero.png" alt="品牌出海全球商业热点横幅" />
    <div class="hero-inner">
      <div class="date">{today} · 品牌出海热点速递</div>
      <h1>全球增长信号正在重新排序</h1>
      <p class="lead">每天自动聚合品牌出海、跨境电商、内容电商、独立站、平台政策、物流支付与合规变化，打开这个网址就能看到最新一版。</p>
      <div class="ticker">{category_html}</div>
    </div>
  </section>

  <main>
    <section class="summary">
      <div class="brief">
        <p class="eyebrow">今日总览</p>
        <h2>今天抓取到 {len(items)} 条高相关资讯，覆盖 {source_count} 个来源</h2>
        <p>这份页面由自动任务生成。建议先看平台经营、内容电商和合规政策相关条目，再决定今天要复盘哪个市场、哪个渠道或哪个 SKU。</p>
        <div class="metric-grid">
          <div class="metric"><strong>{len(items)}</strong><p>条核心热点，点击卡片来源可查看原文。</p></div>
          <div class="metric"><strong>{source_count}</strong><p>个信息来源，降低只看单一平台带来的偏差。</p></div>
          <div class="metric"><strong>09:00</strong><p>每天北京时间上午自动刷新。</p></div>
        </div>
      </div>
      <div class="focus">
        <p class="eyebrow">重点观察</p>
        <h2>今天看什么</h2>
        <ul>
          <li>平台规则或工具变化是否影响现有店铺效率。</li>
          <li>内容电商热点是否能转化为可复用素材和达人策略。</li>
          <li>物流、支付、税务和合规是否改变利润结构。</li>
          <li>海外消费者趋势是否提示新品或卖点调整。</li>
        </ul>
      </div>
    </section>

    <section class="content">
      <div class="cards">
        {cards_html}
      </div>

      <aside>
        <div class="action">
          <p class="eyebrow">今日建议</p>
          <h3>优先做这三件事</h3>
          <ol>
            <li>挑一条与你品类最相关的资讯，拆出市场、渠道、价格和履约影响。</li>
            <li>检查主力 SKU 的商品页、评论痛点和本地化支付是否匹配目标市场。</li>
            <li>把今天看到的内容信号转成 3 条可测试短视频或广告素材角度。</li>
          </ol>
        </div>

        <div class="action">
          <p class="eyebrow">市场雷达</p>
          <h3>长期盯住的方向</h3>
          <div class="market-list">
            <div class="market"><b>美国</b><span>平台竞争强，品牌信任关键</span></div>
            <div class="market"><b>欧洲</b><span>合规复杂，客单与品质更重要</span></div>
            <div class="market"><b>东南亚</b><span>内容电商快，价格敏感</span></div>
            <div class="market"><b>中东</b><span>增长快，本地履约要求高</span></div>
          </div>
        </div>
      </aside>
    </section>
  </main>

  <footer>
    最后更新：{machine_date} Asia/Shanghai。页面仅展示摘要与链接，不转载全文。
  </footer>
</body>
</html>
"""


CSS = r"""
    :root {
      --ink: #172126;
      --muted: #63727a;
      --line: #dce5e7;
      --paper: #f6f8f7;
      --panel: #ffffff;
      --teal: #0b7c75;
      --amber: #d78b22;
      --red: #d24545;
      --blue: #315f9b;
      --shadow: 0 18px 45px rgba(22, 33, 38, 0.12);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: "Inter", "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.55;
    }
    a { color: inherit; text-decoration: none; }
    .hero {
      min-height: 72vh;
      display: grid;
      align-items: end;
      position: relative;
      overflow: hidden;
      color: #fff;
      background: #111;
    }
    .hero img {
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
        linear-gradient(90deg, rgba(8, 18, 22, 0.88), rgba(8, 18, 22, 0.36) 54%, rgba(8, 18, 22, 0.72)),
        linear-gradient(0deg, rgba(8, 18, 22, 0.82), transparent 48%);
    }
    .hero-inner {
      width: min(1180px, calc(100% - 40px));
      margin: 0 auto;
      position: relative;
      z-index: 1;
      padding: 34px 0 54px;
    }
    .date {
      display: inline-flex;
      gap: 10px;
      align-items: center;
      padding: 7px 11px;
      border: 1px solid rgba(255, 255, 255, 0.32);
      background: rgba(255, 255, 255, 0.08);
      font-size: 14px;
      letter-spacing: 0;
    }
    h1 {
      max-width: 780px;
      margin: 22px 0 16px;
      font-size: clamp(42px, 7vw, 84px);
      line-height: 0.96;
      letter-spacing: 0;
    }
    .lead {
      max-width: 720px;
      margin: 0;
      color: rgba(255, 255, 255, 0.82);
      font-size: 18px;
    }
    .ticker {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 30px;
    }
    .ticker span {
      border: 1px solid rgba(255, 255, 255, 0.22);
      background: rgba(255, 255, 255, 0.1);
      padding: 8px 12px;
      font-size: 13px;
    }
    main {
      width: min(1180px, calc(100% - 40px));
      margin: -26px auto 72px;
      position: relative;
      z-index: 2;
    }
    .summary {
      display: grid;
      grid-template-columns: 1.35fr 0.65fr;
      gap: 18px;
      margin-bottom: 22px;
    }
    .brief, .focus, .card, .action {
      background: var(--panel);
      box-shadow: var(--shadow);
      border: 1px solid rgba(220, 229, 231, 0.9);
    }
    .brief, .focus { padding: 22px; }
    .eyebrow {
      color: var(--teal);
      font-weight: 700;
      font-size: 13px;
      margin: 0 0 9px;
    }
    h2, h3 { letter-spacing: 0; line-height: 1.18; }
    h2 { margin: 0 0 10px; font-size: 25px; }
    h3 { margin: 0 0 10px; font-size: 18px; }
    p { margin: 0; color: var(--muted); }
    .metric-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 12px;
      margin-top: 18px;
    }
    .metric {
      border-left: 4px solid var(--teal);
      background: #f3faf8;
      padding: 12px;
      min-height: 92px;
    }
    .metric:nth-child(2) { border-color: var(--amber); background: #fff8ee; }
    .metric:nth-child(3) { border-color: var(--blue); background: #f3f6fb; }
    .metric strong { display: block; font-size: 22px; margin-bottom: 4px; }
    .focus ul { margin: 12px 0 0; padding-left: 18px; color: var(--muted); }
    .content {
      display: grid;
      grid-template-columns: 1fr 320px;
      gap: 22px;
      align-items: start;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }
    .card {
      min-height: 280px;
      padding: 19px;
      display: flex;
      flex-direction: column;
      gap: 13px;
      border-radius: 8px;
    }
    .tag-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 8px;
    }
    .tag {
      display: inline-flex;
      align-items: center;
      width: fit-content;
      padding: 5px 9px;
      background: #eef6f4;
      color: var(--teal);
      font-size: 12px;
      font-weight: 700;
    }
    .heat {
      color: var(--red);
      font-size: 13px;
      font-weight: 700;
      white-space: nowrap;
    }
    .card p { font-size: 14px; }
    .meta { color: #809096; font-size: 12px; }
    .insight {
      margin-top: auto;
      padding-top: 13px;
      border-top: 1px solid var(--line);
      color: #34454c;
      font-size: 14px;
    }
    .source {
      color: var(--blue);
      font-size: 13px;
      font-weight: 700;
    }
    aside { display: grid; gap: 16px; }
    .action { padding: 18px; border-radius: 8px; }
    .action ol { margin: 10px 0 0; padding-left: 20px; color: var(--muted); }
    .action li + li { margin-top: 10px; }
    .market-list { display: grid; gap: 10px; margin-top: 12px; }
    .market {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }
    .market b { color: var(--ink); }
    .market span { color: var(--muted); text-align: right; }
    footer {
      width: min(1180px, calc(100% - 40px));
      margin: 0 auto 36px;
      color: var(--muted);
      font-size: 13px;
    }
    @media (max-width: 900px) {
      .summary, .content, .cards { grid-template-columns: 1fr; }
      .metric-grid { grid-template-columns: 1fr; }
      .hero { min-height: 78vh; }
    }
    @media (max-width: 560px) {
      .hero-inner, main, footer { width: min(100% - 28px, 1180px); }
      h1 { font-size: 42px; }
      .lead { font-size: 16px; }
    }
"""


def main() -> None:
    now = datetime.now(TIMEZONE)
    today = now.strftime("%Y-%m-%d")
    items = collect_items()
    if not items:
        items = fallback_items(today)

    PUBLIC.mkdir(exist_ok=True)
    ASSETS.mkdir(exist_ok=True)
    source_asset = ROOT / "assets" / "global-commerce-hero.png"
    target_asset = ASSETS / "global-commerce-hero.png"
    if source_asset.exists() and not target_asset.exists():
        shutil.copy2(source_asset, target_asset)

    (PUBLIC / "index.html").write_text(render_html(items, now), encoding="utf-8")
    (PUBLIC / "latest.json").write_text(
        json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"generated {PUBLIC / 'index.html'} with {len(items)} items")


if __name__ == "__main__":
    main()
