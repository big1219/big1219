#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
엔진오일 관련 입찰공고 통합 알림 v2 : 나라장터 + 한국전력(KEPCO)
================================================================

[소스 1] 나라장터(조달청) — 검증완료, 바로 동작
  - 조달청_나라장터 입찰공고정보서비스 (data.go.kr 15129394)
  - 엔드포인트: https://apis.data.go.kr/1230000/BidPublicInfoService
  - 물품 검색: getBidPblancListInfoThngPPSSrch, 키워드 파라미터 bidNtceNm
  - 한전/발전자회사 공고 상당수가 나라장터에도 게시되므로, 여기서
    공고·수요기관이 KEPCO 계열이면 🔌 로 라벨링해 함께 잡는다.

[소스 2] 한국전력 공식 API — 진행중 공고 제공 확인됨. 단, 엔드포인트/파라미터 '미확정'
  - 한국전력공사_전자입찰계약정보 (data.go.kr 15148223)
  - 인증키는 '전력데이터개방포털'(https://bigdata.kepco.co.kr) 가입 후 발급
  - ⚠️ 정확한 요청 URL·오퍼레이션명·파라미터명은 아래 fetch_kepco()에
     placeholder 로 비워둠. 추측으로 채우지 않았다.
     전력데이터개방포털 Open-API 매뉴얼(또는 data.go.kr 15148223의 '요청 예시')에서
     확인한 값을 KEPCO_* 상수와 param 매핑에 넣고 KEPCO_ENABLED=True 로 켜면 동작.

[알림 채널] SLACK_WEBHOOK_URL > TELEGRAM_BOT_TOKEN+CHAT_ID > 콘솔
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone

import requests

# ──────────────────────────────────────────────────────────────────────────
# 공통 설정
# ──────────────────────────────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))

KEYWORDS = [
    "엔진오일", "엔진유", "윤활유", "기관용 유류",
    "유압작동유", "유압유", "기어오일", "기어유", "그리스", "디젤기관유",
]

LOOKBACK_DAYS = 2
SEEN_FILE = os.environ.get("G2B_SEEN_FILE", "seen.json")
REQUEST_TIMEOUT = 20
RETRY = 3

# 한전 계열 판별용(나라장터에 뜬 공고의 기관명으로 라벨링). 필요시 추가.
KEPCO_ORG_HINTS = [
    "한국전력", "한전", "KEPCO", "한전케이피에스", "한전KPS",
    "한국수력원자력", "한수원", "한국남동발전", "한국중부발전",
    "한국서부발전", "한국남부발전", "한국동서발전", "한전기술", "한전원자력연료",
]

# ── 나라장터 ──
G2B_SERVICE_KEY = os.environ.get("G2B_SERVICE_KEY", "").strip()
G2B_BASE = "https://apis.data.go.kr/1230000/BidPublicInfoService"
G2B_OP_THNG = "getBidPblancListInfoThngPPSSrch"   # 물품

# ── 한전 (⚠️ 매뉴얼 확인 후 채울 것) ──
KEPCO_ENABLED = False  # 엔드포인트/파라미터 채운 뒤 True 로
KEPCO_SERVICE_KEY = os.environ.get("KEPCO_SERVICE_KEY", "").strip()
# ↓↓↓ 아래 4개는 전력데이터개방포털 매뉴얼/‘요청 예시’에서 확인한 실제 값으로 교체 ↓↓↓
KEPCO_BASE = "https://bigdata.kepco.co.kr/openapi/v1/PLACEHOLDER"  # ← 미확정
KEPCO_OP = "PLACEHOLDER"                                          # ← 미확정(있다면)
KEPCO_KEYWORD_PARAM = "PLACEHOLDER_공고명파라미터"                  # ← 미확정
KEPCO_EXTRA_PARAMS = {}                                           # 기간 등 필수 파라미터


# ──────────────────────────────────────────────────────────────────────────
# 상태(중복방지)
# ──────────────────────────────────────────────────────────────────────────
def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"[warn] seen 로드 실패, 새로 시작: {e}", file=sys.stderr)
    return set()


def save_seen(seen: set) -> None:
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen)[-5000:], f, ensure_ascii=False)


def is_kepco(*texts) -> bool:
    joined = " ".join(t for t in texts if t)
    return any(h in joined for h in KEPCO_ORG_HINTS)


# ──────────────────────────────────────────────────────────────────────────
# 소스 1: 나라장터 (검증완료)
# ──────────────────────────────────────────────────────────────────────────
def _g2b_get(keyword: str, bgn: str, end: str) -> list:
    params = {
        "serviceKey": G2B_SERVICE_KEY,
        "pageNo": 1, "numOfRows": 100,
        "inqryDiv": 1, "inqryBgnDt": bgn, "inqryEndDt": end,
        "type": "json", "bidNtceNm": keyword,
    }
    for attempt in range(1, RETRY + 1):
        try:
            r = requests.get(f"{G2B_BASE}/{G2B_OP_THNG}", params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            try:
                data = r.json()
            except ValueError:
                raise RuntimeError(f"JSON 아님(인증키/파라미터 의심): {r.text[:300]}")
            header = data.get("response", {}).get("header", {})
            if header.get("resultCode") not in (None, "00", "0"):
                raise RuntimeError(f"API 오류 {header.get('resultCode')} {header.get('resultMsg')}")
            items = data.get("response", {}).get("body", {}).get("items", [])
            if items in ("", None):
                return []
            if isinstance(items, dict):
                inner = items.get("item", [])
                return inner if isinstance(inner, list) else [inner]
            return items if isinstance(items, list) else []
        except Exception as e:
            print(f"[warn] 나라장터 '{keyword}' 실패({attempt}/{RETRY}): {e}", file=sys.stderr)
            time.sleep(2 * attempt)
    return []


def fetch_narajangteo(bgn: str, end: str) -> list:
    out = {}
    for kw in KEYWORDS:
        for it in _g2b_get(kw, bgn, end):
            no = it.get("bidNtceNo", "")
            if not no:
                continue
            key = f"G2B-{no}-{it.get('bidNtceOrd','')}"
            rec = {
                "key": key,
                "source": "나라장터",
                "title": it.get("bidNtceNm", ""),
                "no": no,
                "ntce_org": it.get("ntceInsttNm", ""),
                "dmnd_org": it.get("dminsttNm", ""),
                "bid_dt": it.get("bidNtceDt", ""),
                "clse_dt": it.get("bidClseDt", "") or it.get("opengDt", ""),
                "url": it.get("bidNtceDtlUrl", "") or it.get("bidNtceUrl", ""),
                "keyword": kw,
            }
            rec["is_kepco"] = is_kepco(rec["ntce_org"], rec["dmnd_org"], rec["title"])
            out[key] = rec
        time.sleep(0.3)
    return list(out.values())


# ──────────────────────────────────────────────────────────────────────────
# 소스 2: 한국전력 공식 API (스캐폴드 — 매뉴얼 확인 후 활성화)
# ──────────────────────────────────────────────────────────────────────────
def fetch_kepco(bgn: str, end: str) -> list:
    """
    ⚠️ 미완성(의도적): 전력데이터개방포털 매뉴얼에서 확인한 값으로
       KEPCO_BASE / KEPCO_OP / KEPCO_KEYWORD_PARAM / KEPCO_EXTRA_PARAMS 를 채우고
       응답 필드명(공고명/공고번호/기관/마감일/링크)을 아래 매핑에 맞춘 뒤
       KEPCO_ENABLED=True 로 바꾸면 나라장터와 동일 파이프라인으로 합류한다.
    """
    if not KEPCO_ENABLED:
        return []
    if not KEPCO_SERVICE_KEY:
        print("[warn] KEPCO_SERVICE_KEY 없음 — 한전 소스 건너뜀", file=sys.stderr)
        return []

    out = {}
    for kw in KEYWORDS:
        params = {
            "serviceKey": KEPCO_SERVICE_KEY,   # 개방포털 방식에 따라 apiKey/헤더일 수 있음(매뉴얼 확인)
            "returnType": "json",
            KEPCO_KEYWORD_PARAM: kw,
            **KEPCO_EXTRA_PARAMS,              # 기간 등 필수 파라미터(매뉴얼 확인)
        }
        url = KEPCO_BASE if not KEPCO_OP else f"{KEPCO_BASE}/{KEPCO_OP}"
        try:
            r = requests.get(url, params=params, timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f"[warn] 한전 '{kw}' 실패: {e}", file=sys.stderr)
            continue

        # ↓↓↓ 실제 응답 구조에 맞게 items 경로/필드명 교체 ↓↓↓
        items = (data.get("response", {}) or {}).get("body", {}).get("items", []) or data.get("items", [])
        if isinstance(items, dict):
            items = items.get("item", [])
        for it in (items or []):
            no = it.get("공고번호") or it.get("bidNo") or ""     # ← 매뉴얼 필드명으로
            if not no:
                continue
            key = f"KEPCO-{no}"
            out[key] = {
                "key": key,
                "source": "한국전력(공식API)",
                "title": it.get("공고명") or it.get("bidNm") or "",
                "no": no,
                "ntce_org": it.get("기관명") or "한국전력",
                "dmnd_org": "",
                "bid_dt": it.get("공고일자") or "",
                "clse_dt": it.get("마감일시") or it.get("개찰일시") or "",
                "url": it.get("상세URL") or "https://srm.kepco.net",
                "keyword": kw,
                "is_kepco": True,
            }
        time.sleep(0.3)
    return list(out.values())


# ──────────────────────────────────────────────────────────────────────────
# 알림
# ──────────────────────────────────────────────────────────────────────────
def format_item(r: dict) -> str:
    flag = "🔌 " if r.get("is_kepco") else ""
    lines = [
        f"{flag}📢 [{r['source']}·{r['keyword']}] {r['title'] or '(제목없음)'}",
        f"   공고번호: {r['no']}",
        f"   공고기관: {r['ntce_org']}" + (f" / 수요기관: {r['dmnd_org']}" if r.get("dmnd_org") else ""),
        f"   공고일: {r['bid_dt']}   마감/개찰: {r['clse_dt']}",
    ]
    if r.get("url"):
        lines.append(f"   링크: {r['url']}")
    return "\n".join(lines)


def send_slack(text: str) -> bool:
    webhook = os.environ.get("SLACK_WEBHOOK_URL", "").strip()
    if not webhook:
        return False
    requests.post(webhook, json={"text": text}, timeout=REQUEST_TIMEOUT).raise_for_status()
    return True


def send_telegram(text: str) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not (token and chat_id):
        return False
    for chunk in [text[i:i + 3500] for i in range(0, len(text), 3500)]:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True},
            timeout=REQUEST_TIMEOUT,
        ).raise_for_status()
    return True


def notify(items: list) -> None:
    if not items:
        print("새 엔진오일 관련 공고 없음.")
        return
    kepco_n = sum(1 for r in items if r.get("is_kepco"))
    header = (f"🛢️ 엔진오일 관련 신규 입찰공고 {len(items)}건"
              f"{f' (한전계열 {kepco_n}건 포함)' if kepco_n else ''} "
              f"— {datetime.now(KST).strftime('%Y-%m-%d %H:%M')} KST\n")
    message = header + "\n" + "\n\n".join(format_item(r) for r in items)

    if send_slack(message):
        print(f"[ok] Slack 전송 완료 ({len(items)}건)")
    elif send_telegram(message):
        print(f"[ok] Telegram 전송 완료 ({len(items)}건)")
    else:
        print("[info] 알림채널 미설정 → 콘솔 출력\n")
        print(message)


# ──────────────────────────────────────────────────────────────────────────
def main():
    if not G2B_SERVICE_KEY:
        print("[fatal] G2B_SERVICE_KEY 없음 (나라장터 인증키). 최소 이건 필요.", file=sys.stderr)
        sys.exit(1)

    now = datetime.now(KST)
    bgn = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d%H%M")
    end = now.strftime("%Y%m%d%H%M")

    seen = load_seen()

    collected = fetch_narajangteo(bgn, end) + fetch_kepco(bgn, end)
    new_items = [r for r in collected if r["key"] not in seen]

    notify(new_items)

    for r in new_items:
        seen.add(r["key"])
    save_seen(seen)


if __name__ == "__main__":
    main()
