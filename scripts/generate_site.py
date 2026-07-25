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
CURATED_REPORT = ROOT / "content" / "latest.json"
HISTORY_DIR = ROOT / "content" / "history"
REVIEWS_DIR = ROOT / "content" / "reviews"
PUBLIC_HISTORY_DIR = PUBLIC / "history"
TIMEZONE = timezone(timedelta(hours=8))
ITEMS_PER_CATEGORY = 1
MIN_RELEVANCE_SCORE = 2

CATEGORIES = [
    "平台动作",
    "内容趋势",
    "达人/KOL",
    "广告投放",
    "内容电商",
    "品牌案例",
]

QUERIES = [
    "跨境电商 平台运营 最新",
    "Amazon Global Selling seller update brand latest",
    "TikTok Shop 跨境电商 品牌 最新",
    "内容电商 品牌出海 最新",
    "DTC 独立站 品牌出海 最新",
    "Shopify DTC brand global expansion latest",
    "跨境电商 物流 履约 支付 最新",
    "cross-border ecommerce logistics fulfillment payment latest",
    "品牌出海 合规 关税 监管 最新",
    "cross-border ecommerce compliance tariff regulation latest",
    "海外消费者 趋势 品牌出海 最新",
    "global consumer trends ecommerce brand latest",
]

CATEGORY_KEYWORDS = [
    ("平台经营", ["amazon", "temu", "shein", "marketplace", "seller", "平台", "卖家"]),
    ("内容电商", ["tiktok", "creator", "live", "short video", "直播", "达人", "短视频", "内容"]),
    ("DTC 独立站", ["shopify", "dtc", "独立站", "direct-to-consumer", "brand site"]),
    ("物流支付", ["logistics", "shipping", "fulfillment", "payment", "物流", "支付", "履约"]),
    ("合规政策", ["tariff", "compliance", "regulation", "privacy", "关税", "合规", "监管", "税"]),
    ("消费趋势", ["consumer", "trend", "demand", "消费者", "趋势", "需求"]),
]

RELEVANCE_KEYWORDS = [
    "品牌出海",
    "出海",
    "跨境",
    "跨境电商",
    "海外",
    "全球化",
    "amazon",
    "temu",
    "shein",
    "tiktok shop",
    "shopify",
    "dtc",
    "direct-to-consumer",
    "cross border",
    "cross-border",
    "global selling",
    "global expansion",
    "ecommerce",
    "marketplace",
    "seller",
    "logistics",
    "fulfillment",
    "compliance",
    "tariff",
    "consumer",
]

HIGH_VALUE_KEYWORDS = [
    "品牌出海",
    "跨境电商",
    "中国品牌",
    "tiktok shop",
    "amazon global selling",
    "global selling",
    "cross-border",
    "cross border",
    "global expansion",
    "dtc",
    "direct-to-consumer",
]

NOISE_KEYWORDS = [
    "stock",
    "shares",
    "earnings",
    "股价",
    "财报",
    "招聘",
    "job",
    "coupon",
    "优惠券",
]

CATEGORY_COVERS = {
    "平台动作": "cover-platform-updates.png",
    "内容趋势": "cover-content-trends-v2.png",
    "达人/KOL": "cover-creators-v2.png",
    "广告投放": "cover-ads.png",
    "内容电商": "cover-commerce-v2.png",
    "品牌案例": "cover-brand-cases-v2.png",
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
    why: str = ""
    framework: str = ""
    action: str = ""
    confidence: str = ""
    signal_type: str = "已核验事实"
    source_published_at: str = ""
    source_timezone: str = ""
    first_seen_at: str = ""
    event_key: str = ""


def load_curated_report() -> tuple[list[Item], dict]:
    if not CURATED_REPORT.exists():
        return [], {}
    payload = json.loads(CURATED_REPORT.read_text(encoding="utf-8"))
    items = [
        Item(
            title=row["title"],
            link=row["link"],
            source=row["source"],
            published=row["event_date"],
            summary=row["summary"],
            category=row["category"],
            heat=row.get("heat", 90),
            fallback=False,
            why=row.get("why", ""),
            framework=row.get("framework", ""),
            action=row.get("action", ""),
            confidence=row.get("confidence", ""),
            signal_type=row.get("signal_type", "已核验事实"),
            source_published_at=row.get("source_published_at", ""),
            source_timezone=row.get("source_timezone", ""),
            first_seen_at=row.get("first_seen_at", ""),
            event_key=row.get("event_key", ""),
        )
        for row in payload.get("items", [])
    ]
    signal_types = {item.signal_type for item in items}
    allowed_signal_types = {"已核验事实", "行业雷达"}
    if not signal_types.issubset(allowed_signal_types):
        raise RuntimeError(f"Unsupported signal_type values: {sorted(signal_types - allowed_signal_types)}")
    if len(signal_types) > 1:
        raise RuntimeError("A daily report cannot mix verified facts with industry radar items.")
    event_keys = [item.event_key for item in items if item.event_key]
    if len(event_keys) != len(set(event_keys)):
        raise RuntimeError("A daily report contains duplicate event_key values.")
    return items, payload


def archive_report(report: dict) -> None:
    """Keep each published daily report as a source file for later reviews."""
    report_date = report.get("report_date", "")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
        raise ValueError(f"Invalid report_date for archive: {report_date!r}")
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    (HISTORY_DIR / f"{report_date}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_history_reports() -> list[dict]:
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


def load_review_reports() -> list[dict]:
    reviews = []
    if not REVIEWS_DIR.exists():
        return reviews
    for path in sorted(REVIEWS_DIR.glob("*.json"), reverse=True):
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(review, dict) and review.get("period"):
            reviews.append(review)
    return reviews


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
    return "消费趋势"


def relevance_score(item: Item) -> int:
    text = f"{item.title} {item.summary} {item.source}".lower()
    if any(keyword.lower() in text for keyword in NOISE_KEYWORDS):
        return 0
    score = sum(1 for keyword in RELEVANCE_KEYWORDS if keyword.lower() in text)
    score += sum(2 for keyword in HIGH_VALUE_KEYWORDS if keyword.lower() in text)
    score += 1 if item.category in CATEGORIES else 0
    return score


def is_recent(item: Item, now: datetime) -> bool:
    return item.published == now.strftime("%Y-%m-%d")


def is_relevant(item: Item, now: datetime) -> bool:
    return relevance_score(item) >= MIN_RELEVANCE_SCORE and is_recent(item, now)


def published_sort_value(item: Item) -> str:
    return item.published or "0000-00-00"


def heat_for(title: str, summary: str, index: int) -> int:
    text = f"{title} {summary}".lower()
    score = 68 + max(0, 18 - index * 2)
    for _, words in CATEGORY_KEYWORDS:
        score += sum(2 for word in words if word.lower() in text)
    return min(score, 96)


def insight_for(category: str) -> str:
    mapping = {
        "平台动作": "优先判断平台功能、规则和流量入口如何改变内容运营方式。",
        "内容趋势": "把热点拆成可复用的选题、叙事结构和本地化表达。",
        "达人/KOL": "关注达人发现、授权、佣金和长期合作机制，而不是只看粉丝量。",
        "广告投放": "把素材标签、数据回传和增量 ROAS 连起来，避免只看表面播放量。",
        "内容电商": "把短视频、直播、商品页和成交承接放进同一内容链路。",
        "品牌案例": "提炼可复制的内容节奏、创作者组合和市场本地化方法。",
    }
    return mapping.get(category, "判断品牌资产、市场定位和渠道组合是否能支撑长期增长。")


def fetch_google_news(query: str) -> list[Item]:
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans"
    data = fetch_url(url)
    root = ET.fromstring(data)
    items: list[Item] = []
    for index, node in enumerate(root.findall("./channel/item")):
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
    now = datetime.now(TIMEZONE)
    seen: set[str] = set()
    collected: list[Item] = []
    for query in QUERIES:
        try:
            for item in fetch_google_news(query):
                key = re.sub(r"\W+", "", item.title.lower())[:90]
                if key and key not in seen and is_relevant(item, now):
                    seen.add(key)
                    collected.append(item)
        except Exception as exc:
            print(f"warn: failed query {query}: {exc}", file=sys.stderr)

    selected: list[Item] = []
    for category in CATEGORIES:
        candidates = [item for item in collected if item.category == category]
        candidates.sort(
            key=lambda item: (published_sort_value(item), relevance_score(item), item.heat),
            reverse=True,
        )
        selected.extend(candidates[:ITEMS_PER_CATEGORY])

    return selected


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
        "cover-platform-updates.png",
        "cover-ads.png",
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


def keyword_hits(items: list[Item]) -> list[str]:
    groups = [
        ("平台规则", ["amazon", "temu", "shein", "marketplace", "seller", "平台", "卖家", "规则"]),
        ("内容转化", ["tiktok", "creator", "live", "short video", "达人", "直播", "短视频", "内容"]),
        ("独立站资产", ["shopify", "dtc", "独立站", "direct-to-consumer", "brand site"]),
        ("履约成本", ["logistics", "shipping", "fulfillment", "物流", "履约", "配送"]),
        ("合规门槛", ["tariff", "compliance", "regulation", "privacy", "关税", "合规", "监管", "税"]),
        ("海外需求", ["consumer", "trend", "demand", "消费者", "趋势", "需求", "本地化"]),
    ]
    text = " ".join(f"{item.title} {item.summary}" for item in items).lower()
    scored = []
    for label, words in groups:
        score = sum(text.count(word.lower()) for word in words)
        if score:
            scored.append((label, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [label for label, _ in scored[:3]]


def sample_titles(items: list[Item], limit: int = 3) -> str:
    titles = [f"《{item.title}》" for item in items[:limit]]
    if not titles:
        return "今天没有抓到足够稳定的真实资讯"
    return "、".join(titles)


def category_read(category: str) -> str:
    mapping = {
        "平台经营": "它影响的是平台规则、流量入口、店铺效率和平台侧经营成本。",
        "内容电商": "它影响的是内容种草、达人合作、直播短视频转化和商品页承接。",
        "DTC 独立站": "它影响的是自有站转化、复购、一方数据和品牌资产沉淀。",
        "物流支付": "它影响的是履约时效、支付体验、退换货成本和用户评价。",
        "合规政策": "它影响的是关税、认证、隐私、产品安全和上市风险。",
        "消费趋势": "它影响的是海外用户需求、本地化表达、价格敏感度和购买理由。",
    }
    return mapping.get(category, "它影响的是品牌出海的市场选择、渠道组合和长期经营确定性。")


def source_read(item: Item) -> str:
    if item.fallback:
        return "这条是备用观察项，只能作为方向提醒，不能当成当天新闻结论。"
    return f"来源是「{item.source}」，需要点开原文判断它是事实变化、平台公告，还是媒体观察。"


def item_analysis(item: Item, index: int) -> str:
    title = item.title.replace(" - ", "，来自")
    return f"{index:02d}｜{item.category}：{title}。{category_read(item.category)}{source_read(item)}"


def dynamic_analysis_paragraphs(items: list[Item], now: datetime) -> list[str]:
    counts = category_counts(items)
    ordered = [(category, count) for category, count in sorted(counts.items(), key=lambda pair: pair[1], reverse=True) if count]
    top = ordered[0][0] if ordered else "品牌出海"
    second = ordered[1][0] if len(ordered) > 1 else None
    source_count = len({item.source for item in items})
    signals = keyword_hits(items)
    signal_text = "、".join(signals) if signals else f"{top}相关变化"
    examples = sample_titles(items)
    mode, _ = summary_mode(now)
    period = "本期" if mode != "今日分析" else "今天"

    category_text = f"「{top}」"
    if second:
        category_text += f"和「{second}」"

    return [
        f"{period}抓到的 {len(items)} 条资讯来自 {source_count} 个来源，信息重心落在{category_text}。这说明今天更值得看的不是单条新闻的热闹程度，而是这些内容共同暴露出的经营侧重点：{signal_text}正在影响品牌出海的判断顺序。",
        f"从标题层面看，代表性线索包括{examples}。这些内容如果分开看只是新闻，但放在一起看，会指向同一个问题：品牌不能只判断某个平台有没有流量，还要判断这条增长路径能不能被内容、转化、履约和合规同时支撑。",
        f"如果{top}占比最高，说明短期要先检查这一环节有没有改变原来的增长假设。比如平台类信号多，就看规则、流量入口和店铺效率；内容类信号多，就看素材、达人、商品页和库存承接；履约或合规信号变多，则要先算成本、时效和风险，再决定是否加大投放。",
        f"因此，今天这份日报的读法不是追热点，而是把热点当成经营预警。你可以先标记哪些信息会影响选品、定价、渠道和供应链，再决定要不要进入下一步验证。对品牌出海来说，有用的资讯不是最多的资讯，而是能改变决策优先级的资讯。",
    ]


def dynamic_analysis_paragraphs(items: list[Item], now: datetime) -> list[str]:
    real_items = [item for item in items if not item.fallback]
    active_items = real_items or items
    counts = category_counts(active_items)
    ordered = [(category, count) for category, count in sorted(counts.items(), key=lambda pair: pair[1], reverse=True) if count]
    top = ordered[0][0] if ordered else "品牌出海"
    source_count = len({item.source for item in items})
    signals = keyword_hits(active_items)
    signal_text = "、".join(signals) if signals else f"{top}相关变化"
    mode, _ = summary_mode(now)
    period = "本期" if mode != "今日分析" else "今天"

    if not real_items:
        return [
            f"{period}没有抓到严格符合当天日期和品牌出海主题的真实资讯，页面展示的是备用观察项。因此今天不做强结论，只把它当作检查清单。",
            "如果连续几天真实资讯很少，说明筛选条件可能过窄；如果出现明显偏题内容，说明关键词还需要继续收紧。当前优先级是保证资讯真实和相关，而不是为了页面好看硬凑数量。",
            *[item_analysis(item, index) for index, item in enumerate(active_items, start=1)],
        ]

    return [
        f"{period}抓到 {len(real_items)} 条当天真实资讯，来自 {source_count} 个来源。信息最集中的分类是「{top}」，关键词信号主要是：{signal_text}。",
        "今天的综合判断不再做泛泛总结，而是看每条资讯分别影响品牌出海的哪一段经营链路。下面这些判断来自当天标题、来源和分类标签。",
        *[item_analysis(item, index) for index, item in enumerate(real_items, start=1)],
    ]


def render_analysis_paragraphs(items: list[Item], now: datetime) -> str:
    return "\n".join(f"      <p>{html.escape(paragraph)}</p>" for paragraph in dynamic_analysis_paragraphs(items, now))


def cover_for(category: str) -> str:
    return CATEGORY_COVERS.get(category, CATEGORY_COVERS["品牌案例"])


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
    if not items:
        return """
        <article class="news-card empty-state">
          <div class="card-body">
            <div class="card-meta"><span>今日核验结果</span></div>
            <h3>今日暂无通过“具体日期 + 当天新增 + 岗位相关”核验的核心资讯</h3>
            <p>宁缺毋滥：没有用月份级更新时间、旧机制说明或同一平台的背景资料补足卡片。</p>
          </div>
        </article>
        """
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
                  <span class="category-tag">{html.escape(item.category)}</span>
                  <span class="signal-tag">{html.escape(item.signal_type)}</span>
                </div>
                <h3>{html.escape(item.title)}</h3>
                <p>{html.escape(item.summary or "暂无摘要，请点击来源查看详情。")}</p>
                <div class="insight">
                  <strong>为什么值得关注：</strong>{html.escape(item.why or insight_for(item.category))}<br />
                  <strong>框架：</strong>{html.escape(item.framework or item.category)}<br />
                  <strong>可借鉴动作：</strong>{html.escape(item.action or "结合目标市场做一次小规模内容验证。")}
                </div>
                <div class="card-foot">
                  <span>{html.escape(item.source)} · {html.escape(item.published)} · {html.escape(item.confidence)}</span>
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
    source_count = len({item.source for item in items})
    analysis_body = render_analysis_paragraphs(items, now)

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
{analysis_body}
    </section>
  </main>

  <footer>
    最后更新：{machine_date} Asia/Shanghai。季度最后一天自动切换为季度总结；12月31日自动切换为年终总结。
  </footer>
</body>
</html>
"""


def render_html(items: list[Item], now: datetime, report: dict | None = None) -> str:
    report = report or {}
    report_date = report.get("report_date", now.strftime("%Y-%m-%d"))
    try:
        report_day = datetime.strptime(report_date, "%Y-%m-%d").replace(tzinfo=TIMEZONE)
        today = fmt_date(report_day)
    except ValueError:
        today = report_date
    machine_date = now.strftime("%Y-%m-%d %H:%M")
    source_count = len({item.source for item in items})
    top_title = items[0].title if items else "今日暂无可用资讯"
    edition_label = {"morning": "晨间完整版"}.get(report.get("edition"), "当前版")
    scan_start = report.get("scan_window_start", "")
    scan_end = report.get("scan_window_end", "")
    scan_window = f"扫描窗口：{scan_start} — {scan_end}" if scan_start and scan_end else "扫描窗口：待下次自动更新记录"

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
      <a href="#news">热点</a>
      <a href="archive.html">沉淀库</a>
    </nav>
  </header>

  <main>
    <section class="hero">
      <img src="assets/global-commerce-hero.png" alt="出海热点封面" />
      <div class="hero-copy">
        <p class="eyebrow">{today} · Global Brand Intelligence</p>
        <h1>出海热点</h1>
        <p>面向出海内容运营：平台、内容、达人、投放与内容电商的每日核验情报。</p>
      </div>
    </section>

    <section class="data-band">
      <img src="assets/hotspots-data-cover.png" alt="热点数据封面" />
      <div class="data-copy">
        <p class="eyebrow">Daily Signal</p>
        <h2>{len(items)} 条热点，{source_count} 个来源</h2>
        <p>{html.escape(report.get("trend", "优先判断哪些平台与内容变化会改变今天的运营动作。"))}</p>
        <p class="scan-window">{edition_label} · {html.escape(scan_window)}</p>
      </div>
      <div class="data-stats">
        <div><strong>{len(items)}</strong><span>热点</span></div>
        <div><strong>{source_count}</strong><span>来源</span></div>
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


def render_archive_html(history: list[dict], reviews: list[dict], now: datetime) -> str:
    history_rows = []
    for report in history:
        item_count = len(report.get("items", []))
        history_rows.append(
            f"""
            <article class="analysis-source">
              <span>{html.escape(report.get("report_date", ""))}</span>
              <div>
                <h3>{item_count} 条当日情报</h3>
                <p>{html.escape(report.get("trend", "暂无趋势判断。"))}</p>
                <a href="history/{html.escape(report.get("report_date", ""))}.json" target="_blank" rel="noreferrer">查看结构化归档</a>
              </div>
            </article>
            """
        )
    review_rows = []
    for review in reviews:
        review_rows.append(
            f"""
            <article class="analysis-source">
              <span>{html.escape(review.get("period", ""))}</span>
              <div>
                <h3>{html.escape(review.get("title", "阶段总结"))}</h3>
                <p>{html.escape(review.get("summary", ""))}</p>
                <p><strong>建议：</strong>{html.escape(review.get("action", ""))}</p>
              </div>
            </article>
            """
        )
    history_html = "\n".join(history_rows) or "<p>历史归档将在每日发布后自动沉淀。</p>"
    reviews_html = "\n".join(review_rows) or "<p>首份季度/年度总结将在对应周期结束后生成。</p>"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>情报沉淀库 · 品牌出海热点速递</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar">
    <a class="brand" href="./"><span>BG</span>品牌出海热点速递</a>
    <nav><a href="./">首页</a><a href="#reviews">季度/年度总结</a><a href="#history">每日归档</a></nav>
  </header>
  <main class="analysis-page">
    <section class="analysis-hero">
      <p class="eyebrow">Knowledge Archive</p>
      <h1>内容运营情报沉淀库</h1>
      <p>每天保留结构化情报；季度末与年末以这些已保存的来源、类别、市场和行动建议为基础进行复盘。</p>
    </section>
    <section class="analysis-long" id="reviews">
      <h2>季度与年度总结</h2>
      <div class="analysis-sources">{reviews_html}</div>
    </section>
    <section class="analysis-long" id="history">
      <h2>每日归档</h2>
      <p>已沉淀 {len(history)} 期。每期均保留当日结论、行动建议和条目链接，供季度总结追溯。</p>
      <div class="analysis-sources">{history_html}</div>
    </section>
  </main>
  <footer>最后更新：{now.strftime("%Y-%m-%d %H:%M")} Asia/Shanghai。</footer>
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

.data-copy .scan-window {
  font-size: 12px;
  line-height: 1.5;
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

.category-tag {
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(15, 118, 110, .1);
  color: var(--green);
  font-weight: 800;
}

.signal-tag {
  padding: 3px 9px;
  border-radius: 999px;
  background: rgba(15, 23, 42, .08);
  color: var(--muted);
  font-weight: 700;
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
    items, report = load_curated_report()
    if report.get("report_date") != today:
        raise RuntimeError(
            f"Curated report date is {report.get('report_date')!r}, expected Beijing date {today}; "
            "keeping the previous verified deployment."
        )

    PUBLIC.mkdir(exist_ok=True)
    ensure_assets()
    archive_report(report)
    history = load_history_reports()
    reviews = load_review_reports()
    PUBLIC_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    for source in HISTORY_DIR.glob("????-??-??.json"):
        shutil.copy2(source, PUBLIC_HISTORY_DIR / source.name)
    (PUBLIC / "index.html").write_text(render_html(items, now, report), encoding="utf-8")
    (PUBLIC / "archive.html").write_text(render_archive_html(history, reviews, now), encoding="utf-8")
    (PUBLIC / ".nojekyll").write_text("", encoding="utf-8")
    (PUBLIC / "latest.json").write_text(
        json.dumps([item.__dict__ for item in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"generated {PUBLIC / 'index.html'} with {len(items)} items")


if __name__ == "__main__":
    main()
