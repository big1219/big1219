"""한국전력(KEPCO) 전자입찰 계약정보 OpenAPI 호출 + 키워드 필터링.

[출처] 전력데이터개방포털 '전자입찰 계약정보 가이드'
  - 요청URL : https://bigdata.kepco.co.kr/openapi/v1/electContract.do (GET, JSON/XML)
  - 필수    : noticeBeginDate, noticeEndDate(최대 90일), apiKey
  - 선택    : companyId(미입력 시 전체 회사), name, progressState, returnType 등
  - 응답    : {"data": [ {no, name, placeName, noticeDate, presumedPrice,
               bidAttendReqCloseDatetime, endDatetime, purchaseType, companyId,
               progressState, filenlink1, ...} ]}

KEPCO_SERVICE_KEY 가 설정돼 있지 않으면 조용히 건너뛴다(기존 나라장터 알림에
영향을 주지 않기 위함).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import requests

from .api import keyword_match
from .notifier import _fmt_amount

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))

# 가이드 문서의 회사구분 코드표.
COMPANY_NAMES = {
    "COM01": "한국전력공사",
    "COM02": "한국서부발전(주)",
    "COM03": "한국전력국제원자력대학원대학교",
    "COM04": "한국남부발전(주)",
    "COM05": "한국중부발전(주)",
    "COM06": "한국남동발전(주)",
    "COM08": "한국동서발전(주)",
    "COM09": "한국전력기술(주)",
    "COM10": "한전KPS(주)",
    "COM11": "한국전력거래소",
    "COM12": "한국원자력연료(주)",
    "COM14": "한국발전교육원",
    "COM16": "한국해상풍력(주)",
    "COM19": "KAPES주식회사",
}

PURCHASE_TYPES = {
    "Product": "자재구매",
    "ConstructionService": "공사용역",
}

PROGRESS_STATES = {
    "PreAttendProgress": "공고진행",
    "AttendProgress": "입찰진행",
    "Close": "마감",
    "Fail": "유찰",
    "OpenTimed": "개찰",
    "Final": "공고종료",
}


def _fmt_dt(value: str) -> str:
    """'20220919170000' → '2022-09-19 17:00'. 형식이 다르면 원본 반환."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    if len(digits) >= 12:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]} {digits[8:10]}:{digits[10:12]}"
    if len(digits) == 8:
        return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"
    return value or "-"


class KepcoBid:
    """한전 전자입찰 공고 한 건을 표현하는 가벼운 래퍼 (api.Bid 와 같은 방식)."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw

    def _get(self, *keys: str, default: str = "") -> str:
        for key in keys:
            value = self.raw.get(key)
            if value not in (None, "", "-"):
                return str(value)
        return default

    @property
    def notice_no(self) -> str:
        return self._get("no")

    @property
    def company_id(self) -> str:
        return self._get("companyId")

    @property
    def company_name(self) -> str:
        return COMPANY_NAMES.get(self.company_id, self.company_id or "-")

    @property
    def key(self) -> str:
        """나라장터 키와 충돌하지 않도록 KEPCO- 접두어를 붙인다."""
        return f"KEPCO-{self.company_id}-{self.notice_no}"

    @property
    def name(self) -> str:
        """입찰건명. keyword_match() 가 이 속성을 사용한다."""
        return self._get("name")

    @property
    def place(self) -> str:
        return self._get("placeName")

    @property
    def notice_dt(self) -> str:
        return _fmt_dt(self._get("noticeDate", "createDatetime"))

    @property
    def attend_close_dt(self) -> str:
        return _fmt_dt(self._get("bidAttendReqCloseDatetime"))

    @property
    def end_dt(self) -> str:
        return _fmt_dt(self._get("endDatetime"))

    @property
    def amount(self) -> str:
        return self._get("presumedPrice", "presumedAmount")

    @property
    def purchase_type(self) -> str:
        raw = self._get("purchaseType")
        return PURCHASE_TYPES.get(raw, raw or "-")

    @property
    def progress_state(self) -> str:
        raw = self._get("progressState")
        return PROGRESS_STATES.get(raw, raw or "-")

    @property
    def url(self) -> str:
        """API 에 공고 상세 URL 필드는 없다. 첨부파일 링크가 있으면 그걸 쓰고,
        없으면 한전 SRM 메인으로 안내한다."""
        return self._get("filenlink1", default="https://srm.kepco.net")


def _date_range(lookback_hours: int) -> tuple[str, str]:
    """noticeBeginDate / noticeEndDate 를 'YYYYMMDD' (KST) 형식으로 만든다."""
    now = datetime.now(KST)
    begin = now - timedelta(hours=lookback_hours)
    return begin.strftime("%Y%m%d"), now.strftime("%Y%m%d")


def fetch_bids(config) -> list[KepcoBid]:
    """기간 내 한전(전 계열사) 전자입찰 공고를 모두 수집한다.

    companyId 를 지정하지 않으면 전체 회사가 조회된다(가이드의
    '선택인자 미입력' 요청 예시와 동일). 키워드 필터는 로컬에서 수행한다.
    """
    begin_d, end_d = _date_range(config.lookback_hours)
    params = {
        "noticeBeginDate": begin_d,
        "noticeEndDate": end_d,
        "apiKey": config.kepco_api_key,
        "returnType": "json",
    }
    resp = requests.get(
        config.kepco_api_url, params=params, timeout=config.request_timeout
    )
    resp.raise_for_status()
    try:
        payload = resp.json()
    except ValueError as exc:
        raise RuntimeError(
            f"KEPCO JSON 파싱 실패. 응답 일부: {resp.text[:300]}"
        ) from exc

    data = payload.get("data", []) if isinstance(payload, dict) else []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        data = []

    bids = [KepcoBid(item) for item in data if isinstance(item, dict)]
    logger.info("KEPCO 조회 %s~%s: 공고 %d건", begin_d, end_d, len(bids))
    return bids


def find_matching_bids(config) -> list[tuple[KepcoBid, str]]:
    """키워드에 매칭되는 (공고, 키워드) 목록. 키 미설정/오류 시 빈 목록."""
    if not getattr(config, "kepco_api_key", ""):
        logger.info("KEPCO_SERVICE_KEY 미설정 — 한전 조회를 건너뜁니다.")
        return []
    try:
        bids = fetch_bids(config)
    except Exception:  # noqa: BLE001 - 한전 실패가 나라장터 알림을 막지 않도록
        logger.exception("KEPCO 조회 실패")
        return []

    matches: list[tuple[KepcoBid, str]] = []
    for bid in bids:
        matched = keyword_match(bid, config.keywords)
        if matched:
            matches.append((bid, matched))
    return matches


def build_message(bid: KepcoBid, matched_keyword: str) -> str:
    """텔레그램 HTML 포맷 메시지 생성 (notifier.build_message 의 한전 버전)."""
    import html

    e = html.escape
    lines = [
        "🔌 <b>한전(KEPCO) 신규 입찰공고</b>",
        f"🔎 매칭 키워드: <b>{e(matched_keyword)}</b>",
        "",
        f"📌 <b>{e(bid.name)}</b>",
        f"🏢 회사: {e(bid.company_name)}",
    ]
    if bid.place:
        lines.append(f"🏬 발주기관: {e(bid.place)}")
    lines += [
        f"🔢 공고번호: {e(bid.notice_no)}",
        f"📦 구분: {e(bid.purchase_type)} / 상태: {e(bid.progress_state)}",
        f"💰 추정가격: {e(_fmt_amount(bid.amount))}",
        f"🗓 공고일시: {e(bid.notice_dt)}",
        f"⏰ 입찰신청마감: {e(bid.attend_close_dt)}",
        f"🏁 입찰종료: {e(bid.end_dt)}",
        f'🔗 <a href="{e(bid.url)}">첨부/상세 보기</a>',
    ]
    return "\n".join(lines)
