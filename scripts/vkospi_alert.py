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


def _get(url, headers=None, timeout=25):
    h = {"User-Agent": UA, "Accept": "*/*", "Accept-Language": "ko,en;q=0.8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def from_cnbc():
    url = (
        "https://quote.cnbc.com/quote-html-webservice/restQuote/symbolType/symbol"
        "?symbols=.KSVKOSPI&requestMethod=itv&noform=1&partnerId=2&fund=1"
        "&exthrs=1&output=json&events=1"
    )
    data = json.loads(_get(url, headers={"Accept": "application/json"}))
    q = data["FormattedQuoteResult"]["FormattedQuote"][0]
    value = str(q["last"]).replace(",", "")
    change = str(q.get("change", "")).replace(",", "") or None
    pct = q.get("change_pct")
    if pct and not str(pct).endswith("%"):
        pct = f"{pct}%"
    return value, change, pct, "CNBC"


def from_naver():
    last_err = None
    for code in (".VKOSPI", "VKOSPI", "KSVKOSPI"):
        try:
            txt = _get(
                f"https://m.stock.naver.com/api/index/{code}/basic",
                headers={
                    "Accept": "application/json",
                    "Referer": "https://m.stock.naver.com/",
                },
            )
            d = json.loads(txt)
            value = str(d["closePrice"]).replace(",", "")
            change = str(d.get("compareToPreviousClosePrice", "")).replace(",", "") or None
            pct = d.get("fluctuationsRatio")
            if pct and not str(pct).endswith("%"):
                pct = f"{pct}%"
            return value, change, pct, "Naver"
        except Exception as e:
            last_err = e
    raise RuntimeError(f"naver all codes failed: {last_err}")


def from_investing():
    last_err = None
    for url in (
        "https://kr.investing.com/indices/kospi-volatility",
        "https://www.investing.com/indices/kospi-volatility",
    ):
        try:
            html = _get(url, headers={"Accept": "text/html,application/xhtml+xml"})
        except Exception as e:
            last_err = e
            continue

        def s(pats):
            for p in pats:
                m = re.search(p, html)
                if m:
                    return m.group(1).strip()
            return None

        value = s([r'data-test="instrument-price-last"[^>]*>([\d,\.]+)<'])
        if value:
            change = s([r'data-test="instrument-price-change"[^>]*>([+\-]?[\d,\.]+)<'])
            pct = s([r'data-test="instrument-price-change-percent"[^>]*>\(?([+\-]?[\d,\.]+%)\)?<'])
            return value.replace(",", ""), (change or "").replace(",", "") or None, pct, "Investing.com"
        last_err = RuntimeError(f"price pattern not found: {url}")
    raise RuntimeError(f"investing failed: {last_err}")


SOURCES = [from_cnbc, from_naver, from_investing]


def fetch_vkospi():
    errors = []
    for fn in SOURCES:
        try:
            value, change, pct, src = fn()
            print(f"[ok] source={src} value={value} change={change} pct={pct}")
            return value, change, pct, src
        except Exception as e:
            print(f"[fail] {fn.__name__}: {type(e).__name__}: {e}", file=sys.stderr)
            errors.append(f"{fn.__name__}: {type(e).__name__}: {e}")
    raise RuntimeError("모든 출처 실패 →\n" + "\n".join(errors))


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
    value, change, pct, src = fetch_vkospi()
    try:
        note = interpret(float(value))
    except ValueError:
        note = ""
    parts = ["📊 *코스피 변동성지수 (VKOSPI)*", "", f"현재: *{value}*"]
    if change or pct:
        chg = " ".join(x for x in [change, f"({pct})" if pct else None] if x)
        parts.append(f"전일대비: {chg}")
    if note:
        parts.append(f"상태: {note}")
    parts.append("")
    parts.append(f"_출처: {src}_")
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
    if not json.loads(body).get("ok"):
        raise RuntimeError(f"telegram send failed: {body}")


def main():
    try:
        msg = build_message()
    except Exception as e:
        msg = f"⚠️ VKOSPI 조회 실패: {e}"
        print(msg, file=sys.stderr)
    send_telegram(msg)
    print("--- sent ---\n" + msg)


if __name__ == "__main__":
    main()
