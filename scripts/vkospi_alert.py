#!/usr/bin/env python3
"""코스피 변동성지수(VKOSPI) 일일 알림 스크립트."""
import json
import os
import re
import sys
import urllib.request

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)

SOURCES = [
    "https://kr.investing.com/indices/kospi-volatility",
    "https://www.investing.com/indices/kospi-volatility",
]


def _http_get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "ko,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _search(patterns, html):
    for p in patterns:
        m = re.search(p, html)
        if m:
            return m.group(1).strip()
    return None


def fetch_vkospi():
    last_err = None
    for url in SOURCES:
        try:
            html = _http_get(url)
        except Exception as e:
            last_err = e
            continue
        value = _search([r'data-test="instrument-price-last"[^>]*>([\d,\.]+)<'], html)
        change = _search([r'data-test="instrument-price-change"[^>]*>([+\-]?[\d,\.]+)<'], html)
        pct = _search(
            [r'data-test="instrument-price-change-percent"[^>]*>\(?([+\-]?[\d,\.]+%)\)?<'],
            html,
        )
        if value:
            return (
                value.replace(",", ""),
                change.replace(",", "") if change else None,
                pct if pct else None,
                url,
            )
        last_err = RuntimeError(f"price pattern not found: {url}")
    raise RuntimeError(f"VKOSPI fetch failed: {last_err}")


def interpret(value):
    if value < 20:
        return "🟢 안정 구간"
    if value < 30:
        return "🟡 보통"
    if value < 50:
        return "🟠 변동성 큼 — 주의"
    if value < 70:
        return "🔴 시스템리스크 경계"
    return "⚫ 패닉 구간"


def build_message():
    value, change, pct, url = fetch_vkospi()
    try:
        note = interpret(float(value))
    except ValueError:
        note = ""
    parts = ["📊 *코스피 변동성지수 (VKOSPI)*", "", f"현재: *{value}*"]
    if change is not None or pct is not None:
        chg = " ".join(x for x in [change, f"({pct})" if pct else None] if x)
        parts.append(f"전일대비: {chg}")
    if note:
        parts.append(f"상태: {note}")
    parts.append("")
    parts.append(f"[Investing.com에서 보기]({url})")
    return "\n".join(parts)


def send_telegram(text):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    payload = json.dumps(
        {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=25) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    result = json.loads(body)
    if not result.get("ok"):
        raise RuntimeError(f"telegram send failed: {body}")


def main():
    try:
        msg = build_message()
    except Exception as e:
        msg = f"⚠️ VKOSPI 조회에 실패했어요: {e}"
        print(msg, file=sys.stderr)
    send_telegram(msg)
    print("sent:\n" + msg)


if __name__ == "__main__":
    main()
