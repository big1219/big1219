"""텔레그램 알림 전송."""

from __future__ import annotations

import html
import logging

import requests

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def _fmt_amount(amount: str) -> str:
    """예산 금액을 원화 천단위 콤마로. 숫자가 아니면 원본 반환."""
    try:
        return f"{int(float(amount)):,}원"
    except (TypeError, ValueError):
        return amount or "-"


def build_message(bid, matched_keyword: str) -> str:
    """텔레그램 HTML 포맷 메시지 생성."""
    e = html.escape
    lines = [
        "🛢️ <b>나라장터 신규 입찰공고</b>",
        f"🔎 매칭 키워드: <b>{e(matched_keyword)}</b>",
        "",
        f"📌 <b>{e(bid.name)}</b>",
        f"🏢 공고기관: {e(bid.institution) or '-'}",
    ]
    if bid.demand_institution and bid.demand_institution != bid.institution:
        lines.append(f"🏬 수요기관: {e(bid.demand_institution)}")
    lines += [
        f"🔢 공고번호: {e(bid.notice_no)}-{e(bid.notice_ord)}",
        f"💰 예산: {e(_fmt_amount(bid.amount))}",
        f"🗓 공고일시: {e(bid.notice_dt) or '-'}",
        f"⏰ 입찰마감: {e(bid.close_dt) or '-'}",
        f"📂 개찰일시: {e(bid.opening_dt) or '-'}",
    ]
    if bid.url:
        lines.append(f'🔗 <a href="{e(bid.url)}">공고 상세 보기</a>')
    return "\n".join(lines)


def send_telegram(token: str, chat_id: str, text: str, timeout: int = 30) -> None:
    resp = requests.post(
        TELEGRAM_API.format(token=token),
        json={
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=timeout,
    )
    if resp.status_code != 200:
        raise RuntimeError(
            f"텔레그램 전송 실패 status={resp.status_code} body={resp.text[:300]}"
        )
