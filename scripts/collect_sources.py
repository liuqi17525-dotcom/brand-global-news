"""Collect public Guoxue signals from platform-indexed news RSS feeds."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import ssl
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "site.config.json"
OUTPUT_FILE = ROOT / "content" / "materials.json"
TIMEZONE = timezone(timedelta(hours=8))
USER_AGENT = "Mozilla/5.0 (compatible; GuoxueAIRadar/1.0; +https://github.com/liuqi17525-dotcom/brand-global-news)"

TOPIC_QUERIES = {
    # Put the cross-over theme first so deduplication keeps the more specific label.
    "数字国学": '("国学" OR "传统文化" OR "古籍") ("AI" OR "人工智能" OR "数字化")',
    "经典文化": '"国学" OR "古籍" OR "诗词" OR "儒家" OR "道家" OR "文言文"',
    "非遗民俗": '"非遗" OR "传统文化" OR "戏曲" OR "书法" OR "汉服" OR "茶文化"',
    "易学民俗": '"易经" OR "周易" OR "风水" OR "命理" OR "民俗文化"',
    "中医文化": '"中医文化" OR "黄帝内经" OR "本草纲目" OR "中医养生"',
}
TOPIC_WORDS = {
    "数字国学": ("ai", "人工智能", "数字化", "大模型", "数字人"),
    "经典文化": ("国学", "古籍", "诗词", "儒家", "道家", "文言文", "chinese philosophy"),
    "非遗民俗": ("非遗", "传统文化", "戏曲", "书法", "汉服", "茶文化", "traditional chinese culture"),
    "易学民俗": ("易经", "周易", "风水", "命理", "民俗文化"),
    "中医文化": ("中医文化", "黄帝内经", "本草纲目", "中医养生"),
}


def clean_text(value: str | None) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def matches_topic(text: str, topic: str) -> bool:
    lowered = text.casefold()
    if topic == "数字国学":
        digital = any(word in lowered for word in TOPIC_WORDS[topic])
        culture = any(word in lowered for word in ("国学", "传统文化", "古籍", "诗词", "非遗", "chinese culture"))
        return digital and culture
    return any(word in lowered for word in TOPIC_WORDS[topic])


def parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(TIMEZONE)
    except (TypeError, ValueError, OverflowError):
        return None


def google_news_url(source: dict, topic_query: str) -> str:
    query = f"site:{source['domain']} ({topic_query})"
    encoded = urllib.parse.urlencode({"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"})
    return f"https://news.google.com/rss/search?{encoded}"


def fetch(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml, text/xml"})
    context = ssl.create_default_context()
    with urllib.request.urlopen(request, timeout=timeout, context=context) as response:
        return response.read()


def parse_feed(payload: bytes, source: dict, topic: str, cutoff: datetime, limit: int) -> list[dict]:
    root = ET.fromstring(payload)
    entries = root.findall(".//item")
    results = []
    for entry in entries:
        title = clean_text(entry.findtext("title"))
        url = clean_text(entry.findtext("link"))
        description = clean_text(entry.findtext("description"))
        published = parse_date(entry.findtext("pubDate"))
        publisher = clean_text(entry.findtext("source")) or source["name"]
        if not title or not url:
            continue
        if published and published < cutoff:
            continue
        if not matches_topic(f"{title} {description}", topic):
            continue
        results.append({
            "id": hashlib.sha1(url.encode("utf-8")).hexdigest()[:12],
            "platform": source["name"],
            "topic": topic,
            "kind": source.get("kind", "公开内容"),
            "title": title,
            "summary": description[:240],
            "url": url,
            "published": (published or datetime.now(TIMEZONE)).strftime("%Y-%m-%d"),
            "source": publisher,
        })
        if len(results) >= limit:
            break
    return results


def load_previous() -> dict:
    if not OUTPUT_FILE.exists():
        return {}
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def collect() -> dict:
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    now = datetime.now(TIMEZONE)
    cutoff = now - timedelta(days=int(config.get("lookback_days", 14)))
    limit = int(config.get("items_per_source", 8))
    per_topic_limit = max(1, (limit + len(TOPIC_QUERIES) - 1) // len(TOPIC_QUERIES))
    items: list[dict] = []
    statuses = []
    seen = set()

    for source in config.get("sources", []):
        source_items = []
        errors = []
        try:
            for topic, topic_query in TOPIC_QUERIES.items():
                try:
                    source_items.extend(parse_feed(fetch(google_news_url(source, topic_query)), source, topic, cutoff, per_topic_limit))
                except Exception as exc:
                    errors.append(f"{topic}: {exc}")
            for item in source_items[:limit]:
                key = re.sub(r"\W+", "", item["title"].casefold())[:100]
                if key and key not in seen:
                    seen.add(key)
                    items.append(item)
            is_ok = len(errors) < len(TOPIC_QUERIES)
            statuses.append({"platform": source["name"], "ok": is_ok, "count": len(source_items[:limit]), "checked_at": now.isoformat(timespec="minutes"), "error": "; ".join(errors)[:120] if errors else ""})
            print(f"ok: {source['name']}: {len(source_items[:limit])} item(s)")
        except Exception as exc:  # one source must not stop the complete radar
            statuses.append({"platform": source["name"], "ok": False, "count": 0, "checked_at": now.isoformat(timespec="minutes"), "error": str(exc)[:120]})
            print(f"warn: {source['name']}: {exc}", file=sys.stderr)

    items.sort(key=lambda item: item.get("published", ""), reverse=True)
    if not items:
        previous = load_previous().get("items") or []
        if previous:
            items = previous
            print("warn: all live sources failed; retaining the previous snapshot", file=sys.stderr)

    return {
        "report_date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(timespec="minutes"),
        "items": items,
        "source_status": statuses,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fetch without writing content/materials.json")
    args = parser.parse_args()
    report = collect()
    if args.check:
        print(json.dumps({"items": len(report["items"]), "sources": report["source_status"]}, ensure_ascii=False, indent=2))
        return
    OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(report['items'])} item(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
