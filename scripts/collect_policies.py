"""Monitor official platform policy pages relevant to Guoxue publishing."""

from __future__ import annotations

import hashlib
import json
import re
import ssl
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG_FILE = ROOT / "site.config.json"
OUTPUT_FILE = ROOT / "content" / "policies.json"
LIVE_SNAPSHOT = "https://liuqi17525-dotcom.github.io/brand-global-news/data/policies.json"
TIMEZONE = timezone(timedelta(hours=8))
USER_AGENT = "Mozilla/5.0 (compatible; GuoxueComplianceRadar/1.0)"

RISK_TERMS = {
    "封建迷信": ("封建迷信", "迷信", "算命", "占卜", "改运", "消灾", "风水", "命理"),
    "医疗健康": ("医疗", "中医", "诊断", "治疗", "疾病", "疗效", "养生", "健康"),
    "宗教": ("宗教", "邪教", "佛教", "道教", "法事"),
    "商业推广": ("广告", "推广", "营销", "牟利", "引流", "交易", "商品", "资质"),
    "夸大承诺": ("保证", "绝对", "百分之百", "第一", "唯一", "改变命运", "招财", "转运"),
    "历史文化": ("历史", "传统文化", "英烈", "民族文化", "古籍"),
    "谣言": ("谣言", "虚假信息", "伪科学", "不实信息"),
}


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"script", "style", "svg", "noscript"}:
            self.skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "svg", "noscript"} and self.skip:
            self.skip -= 1

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def clean_text(payload: bytes) -> str:
    raw = payload.decode("utf-8", errors="ignore")
    parser = TextExtractor()
    parser.feed(raw)
    text = unescape(" ".join(parser.parts))
    return re.sub(r"\s+", " ", text).strip()


def fetch_json(url: str, timeout: int = 12) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_page(url: str, timeout: int = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"})
    with urllib.request.urlopen(request, timeout=timeout, context=ssl.create_default_context()) as response:
        return response.read(2_000_000)


def previous_snapshot() -> dict:
    try:
        live = fetch_json(LIVE_SNAPSHOT)
        if isinstance(live, dict) and live.get("policies"):
            return live
    except Exception:
        pass
    try:
        return json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {"policies": []}


def excerpts(text: str, terms: tuple[str, ...], limit: int = 2) -> list[str]:
    found = []
    for term in terms:
        for match in re.finditer(re.escape(term), text, flags=re.IGNORECASE):
            start = max(0, match.start() - 55)
            end = min(len(text), match.end() + 95)
            snippet = text[start:end].strip(" ，。;；")
            if snippet and snippet not in found:
                found.append(snippet)
            if len(found) >= limit:
                return found
    return found


def collect() -> dict:
    config = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    old = {p.get("platform"): p for p in previous_snapshot().get("policies", [])}
    now = datetime.now(TIMEZONE)
    policies = []

    for source in config.get("policy_sources", []):
        prior = old.get(source["platform"], {})
        item = {**source, "checked_at": now.isoformat(timespec="minutes"), "official": True}
        try:
            text = clean_text(fetch_page(source["url"]))
            if len(text) < 80:
                raise RuntimeError("页面正文过短，可能需要浏览器渲染")
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            prior_digest = prior.get("content_hash")
            item.update({
                "available": True,
                "content_hash": digest,
                "change_status": "changed" if prior_digest and prior_digest != digest else ("unchanged" if prior_digest else "baseline"),
                "text_length": len(text),
                "matches": [],
            })
            for category, terms in RISK_TERMS.items():
                snippets = excerpts(text, terms)
                if snippets:
                    item["matches"].append({"category": category, "snippets": snippets})
        except Exception as exc:
            item.update({
                "available": False,
                "change_status": "unreachable",
                "error": str(exc)[:160],
                "content_hash": prior.get("content_hash", ""),
                "matches": prior.get("matches", []),
            })
        policies.append(item)
        print(f"{source['platform']}: {item['change_status']}")

    return {
        "report_date": now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(timespec="minutes"),
        "disclaimer": "仅提供平台运营风险提示，不构成法律意见；发布前请回到平台官方规则核验。",
        "policies": policies,
    }


def main() -> None:
    report = collect()
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_FILE.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {len(report['policies'])} policy source(s) to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
