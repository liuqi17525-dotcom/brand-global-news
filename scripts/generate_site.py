import html
import json
import re
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
            "User-Agent": "Mozilla/5.0 brand-global-news/2.0",
            "Accept": "application/rss+xml, application/xml, text/xml",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def strip_tags(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


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
    score = 68 + max(0, 16 - index * 2)
    for _, words in CATEGORY_KEYWORDS:
        score += sum(2 for word in words if word.lower() in text)
    return min(score, 96)


def insight_for(category: str) -> str:
    mapping = {
        "内容电商": "把达人、素材、商品页和库存联动起来，避免只有流量没有稳定转化。",
        "平台经营": "用平台验证市场和价格带，同时把评价、品牌资产和用户反馈沉淀下来。",
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
            summary="自动资讯源暂时不可用，先展示稳定观察项。每日任务会在 GitHub 云端重新抓取最新来源。",
            category=category,
            heat=88 - index * 3,
        )
        for index, (title, link, source, category) in enumerate(seeds)
    ]


def fmt_date(now: datetime) -> str:
    return f"{now.year}年{now.month}月{now.day}日"


def render_radar(categories: list[str]) -> str:
    labels = categories[:6] or ["平台经营", "内容电商", "DTC 独立站", "物流支付"]
    return "".join(
        f'<span class="radar-chip" style="--i:{index}">{html.escape(label)}</span>'
        for index, label in enumerate(labels)
    )


def render_cards(items: list[Item]) -> str:
    cards = []
    for index, item in enumerate(items, start=1):
        cards.append(
            f"""
            <article class="news-card">
              <div class="card-top">
                <span class="rank">{index:02d}</span>
                <span class="tag">{html.escape(item.category)}</span>
                <span class="heat">热度 {item.heat}</span>
              </div>
              <h3>{html.escape(item.title)}</h3>
              <p>{html.escape(item.summary or "暂无摘要，请点击来源查看原文。")}</p>
              <div class="insight">启示：{html.escape(insight_for(item.category))}</div>
              <div class="card-bottom">
                <span>{html.escape(item.source)} · {html.escape(item.published)}</span>
                <a href="{html.escape(item.link)}" target="_blank" rel="noreferrer">来源</a>
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
    avg_heat = round(sum(item.heat for item in items) / max(len(items), 1))
    cards_html = render_cards(items)
    radar_html = render_radar(categories)

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
  <header class="topbar">
    <a class="brand" href="./" aria-label="品牌出海热点速递首页">
      <span class="brand-mark">BG</span>
      <span>品牌出海热点速递</span>
    </a>
    <div class="top-meta">
      <span>{today}</span>
      <span>北京时间 09:00 自动更新</span>
    </div>
  </header>

  <main>
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Global Brand Intelligence</p>
        <h1>今天的出海信号</h1>
        <p class="lead">聚合品牌出海、跨境电商、内容电商、DTC 独立站、物流支付与合规动态。少一点花哨，多一点能直接看懂的经营线索。</p>
      </div>
      <div class="radar-panel" aria-label="热点雷达">
        <div class="radar-grid">
          <div class="radar-core">
            <strong>{avg_heat}</strong>
            <span>平均热度</span>
          </div>
          {radar_html}
        </div>
      </div>
    </section>

    <section class="stats">
      <div class="stat">
        <span>热点</span>
        <strong>{len(items)}</strong>
        <p>条高相关资讯</p>
      </div>
      <div class="stat">
        <span>来源</span>
        <strong>{source_count}</strong>
        <p>个信息来源</p>
      </div>
      <div class="stat">
        <span>更新</span>
        <strong>09:00</strong>
        <p>每天自动刷新</p>
      </div>
      <div class="stat">
        <span>重点</span>
        <strong>{html.escape(categories[0] if categories else "品牌出海")}</strong>
        <p>今日高频主题</p>
      </div>
    </section>

    <section class="layout">
      <div class="main-column">
        <div class="section-title">
          <p class="eyebrow">News Feed</p>
          <h2>今日热点</h2>
        </div>
        <div class="news-grid">
          {cards_html}
        </div>
      </div>

      <aside class="side-column">
        <section class="panel">
          <p class="eyebrow">Action List</p>
          <h2>今天先做三件事</h2>
          <ol>
            <li>挑一条与你品类最相关的资讯，拆出市场、渠道、价格和履约影响。</li>
            <li>检查主力 SKU 的商品页、评论痛点和本地化支付是否匹配目标市场。</li>
            <li>把今天的内容信号转成 3 条短视频、广告或邮件素材角度。</li>
          </ol>
        </section>

        <section class="panel">
          <p class="eyebrow">Market Watch</p>
          <h2>市场雷达</h2>
          <div class="market-list">
            <div><b>美国</b><span>平台竞争强，品牌信任关键</span></div>
            <div><b>欧洲</b><span>合规复杂，品质与认证更重要</span></div>
            <div><b>东南亚</b><span>内容电商快，价格敏感</span></div>
            <div><b>中东</b><span>增长快，本地履约要求高</span></div>
          </div>
        </section>
      </aside>
    </section>
  </main>

  <footer>
    最后更新：{machine_date} Asia/Shanghai。页面仅展示摘要与来源链接，不转载全文。
  </footer>
</body>
</html>
"""


CSS = r"""
    :root {
      --bg: #f4f6f8;
      --panel: #ffffff;
      --ink: #172026;
      --muted: #63717a;
      --line: #dce3e7;
      --green: #0f766e;
      --blue: #245a92;
      --gold: #b7791f;
      --red: #c24141;
      --shadow: 0 14px 36px rgba(23, 32, 38, 0.08);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background:
        linear-gradient(180deg, #e9eef2 0, #f4f6f8 280px),
        var(--bg);
      color: var(--ink);
      font-family: Inter, "PingFang SC", "Microsoft YaHei", Arial, sans-serif;
      line-height: 1.55;
    }

    a { color: inherit; text-decoration: none; }

    .topbar {
      height: 72px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      width: min(1220px, calc(100% - 40px));
      margin: 0 auto;
    }

    .brand {
      display: inline-flex;
      align-items: center;
      gap: 12px;
      font-weight: 800;
      letter-spacing: 0;
    }

    .brand-mark {
      width: 36px;
      height: 36px;
      display: grid;
      place-items: center;
      background: var(--ink);
      color: #fff;
      border-radius: 8px;
      font-size: 13px;
    }

    .top-meta {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 8px 14px;
      color: var(--muted);
      font-size: 13px;
    }

    main {
      width: min(1220px, calc(100% - 40px));
      margin: 0 auto 58px;
    }

    .hero {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 390px;
      gap: 22px;
      align-items: stretch;
      padding: 24px 0 20px;
    }

    .hero-copy,
    .radar-panel,
    .stat,
    .news-card,
    .panel {
      background: rgba(255, 255, 255, 0.9);
      border: 1px solid rgba(220, 227, 231, 0.9);
      box-shadow: var(--shadow);
      border-radius: 8px;
    }

    .hero-copy {
      min-height: 310px;
      padding: 34px;
      display: flex;
      flex-direction: column;
      justify-content: flex-end;
      background:
        linear-gradient(135deg, rgba(15, 118, 110, 0.12), transparent 42%),
        linear-gradient(90deg, #fff, #f7fafb);
      position: relative;
      overflow: hidden;
    }

    .hero-copy::after {
      content: "";
      position: absolute;
      right: 30px;
      top: 30px;
      width: 220px;
      height: 220px;
      border: 1px solid rgba(36, 90, 146, 0.22);
      border-radius: 50%;
      box-shadow: inset 0 0 0 28px rgba(15, 118, 110, 0.04), inset 0 0 0 70px rgba(183, 121, 31, 0.04);
    }

    .eyebrow {
      margin: 0 0 10px;
      color: var(--green);
      font-size: 12px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0;
    }

    h1, h2, h3, p { margin: 0; }

    h1 {
      max-width: 680px;
      font-size: clamp(44px, 7vw, 82px);
      line-height: 0.98;
      letter-spacing: 0;
      position: relative;
      z-index: 1;
    }

    .lead {
      max-width: 720px;
      margin-top: 18px;
      color: var(--muted);
      font-size: 17px;
      position: relative;
      z-index: 1;
    }

    .radar-panel {
      padding: 22px;
      min-height: 310px;
      display: grid;
      place-items: center;
      background: #101820;
      color: #fff;
      overflow: hidden;
    }

    .radar-grid {
      width: min(300px, 100%);
      aspect-ratio: 1;
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 50%;
      position: relative;
      background:
        radial-gradient(circle, rgba(255, 255, 255, 0.16) 0 2px, transparent 3px),
        radial-gradient(circle, transparent 0 30%, rgba(255,255,255,0.08) 31% 31.5%, transparent 32% 55%, rgba(255,255,255,0.08) 56% 56.5%, transparent 57%);
      background-size: 28px 28px, 100% 100%;
    }

    .radar-core {
      position: absolute;
      inset: 50% auto auto 50%;
      transform: translate(-50%, -50%);
      width: 112px;
      height: 112px;
      display: grid;
      place-items: center;
      text-align: center;
      background: #fff;
      color: var(--ink);
      border-radius: 50%;
      box-shadow: 0 10px 24px rgba(0, 0, 0, 0.28);
    }

    .radar-core strong { display: block; font-size: 34px; line-height: 1; }
    .radar-core span { display: block; color: var(--muted); font-size: 12px; }

    .radar-chip {
      position: absolute;
      left: 50%;
      top: 50%;
      transform:
        rotate(calc(var(--i) * 55deg))
        translate(118px)
        rotate(calc(var(--i) * -55deg));
      transform-origin: 0 0;
      padding: 6px 9px;
      background: rgba(255, 255, 255, 0.12);
      border: 1px solid rgba(255, 255, 255, 0.18);
      border-radius: 999px;
      font-size: 12px;
      white-space: nowrap;
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 14px;
      margin-bottom: 24px;
    }

    .stat {
      padding: 18px;
      min-height: 118px;
    }

    .stat span {
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 8px;
    }

    .stat strong {
      display: block;
      font-size: 30px;
      line-height: 1.05;
    }

    .stat p {
      color: var(--muted);
      margin-top: 8px;
      font-size: 13px;
    }

    .layout {
      display: grid;
      grid-template-columns: minmax(0, 1fr) 340px;
      gap: 22px;
      align-items: start;
    }

    .section-title {
      margin-bottom: 12px;
    }

    .section-title h2,
    .panel h2 {
      font-size: 24px;
      line-height: 1.16;
    }

    .news-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 14px;
    }

    .news-card {
      min-height: 292px;
      padding: 18px;
      display: flex;
      flex-direction: column;
      gap: 12px;
    }

    .card-top {
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .rank {
      color: var(--muted);
      font-weight: 800;
      font-size: 13px;
    }

    .tag {
      padding: 5px 9px;
      background: #eaf5f3;
      color: var(--green);
      border-radius: 999px;
      font-size: 12px;
      font-weight: 800;
    }

    .heat {
      margin-left: auto;
      color: var(--red);
      font-size: 12px;
      font-weight: 800;
      white-space: nowrap;
    }

    .news-card h3 {
      font-size: 18px;
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

    .card-bottom {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      color: var(--muted);
      font-size: 12px;
    }

    .card-bottom a {
      color: var(--blue);
      font-weight: 800;
    }

    .side-column {
      display: grid;
      gap: 14px;
      position: sticky;
      top: 16px;
    }

    .panel {
      padding: 20px;
    }

    .panel ol {
      margin: 14px 0 0;
      padding-left: 20px;
      color: var(--muted);
    }

    .panel li + li {
      margin-top: 10px;
    }

    .market-list {
      display: grid;
      gap: 0;
      margin-top: 14px;
    }

    .market-list div {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      padding: 11px 0;
      border-bottom: 1px solid var(--line);
      font-size: 14px;
    }

    .market-list span {
      color: var(--muted);
      text-align: right;
    }

    footer {
      width: min(1220px, calc(100% - 40px));
      margin: 0 auto 36px;
      color: var(--muted);
      font-size: 13px;
    }

    @media (max-width: 980px) {
      .hero,
      .layout {
        grid-template-columns: 1fr;
      }

      .stats,
      .news-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }

      .side-column {
        position: static;
      }
    }

    @media (max-width: 640px) {
      .topbar,
      main,
      footer {
        width: min(100% - 28px, 1220px);
      }

      .topbar {
        height: auto;
        padding: 18px 0 8px;
        align-items: flex-start;
        flex-direction: column;
      }

      .hero-copy {
        min-height: 300px;
        padding: 24px;
      }

      h1 {
        font-size: 44px;
      }

      .stats,
      .news-grid {
        grid-template-columns: 1fr;
      }

      .radar-chip {
        transform:
          rotate(calc(var(--i) * 55deg))
          translate(100px)
          rotate(calc(var(--i) * -55deg));
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
    (PUBLIC / "index.html").write_text(render_html(items, now), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    (PUBLIC / "latest.json").write_text(
        json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"generated {PUBLIC / 'index.html'} with {len(items)} items")


if __name__ == "__main__":
    main()
