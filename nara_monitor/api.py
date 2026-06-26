"""나라장터 입찰공고정보서비스 OpenAPI 호출 + 키워드 필터링."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable

import requests

logger = logging.getLogger(__name__)

# 한국 표준시(KST). 나라장터 공고게시일시는 KST 기준이다.
KST = timezone(timedelta(hours=9))


class Bid:
    """입찰공고 한 건을 표현하는 가벼운 래퍼."""

    def __init__(self, raw: dict[str, Any]):
        self.raw = raw

    def _get(self, *keys: str, default: str = "") -> str:
        for key in keys:
            value = self.raw.get(key)
            if value not in (None, ""):
                return str(value)
        return default

    @property
    def notice_no(self) -> str:
        return self._get("bidNtceNo")

    @property
    def notice_ord(self) -> str:
        return self._get("bidNtceOrd")

    @property
    def key(self) -> str:
        """공고번호 + 차수 로 중복 판별."""
        return f"{self.notice_no}-{self.notice_ord}"

    @property
    def name(self) -> str:
        return self._get("bidNtceNm")

    @property
    def institution(self) -> str:
        return self._get("ntceInsttNm", "dminsttNm")

    @property
    def demand_institution(self) -> str:
        return self._get("dminsttNm")

    @property
    def notice_dt(self) -> str:
        return self._get("bidNtceDt", "rgstDt")

    @property
    def close_dt(self) -> str:
        return self._get("bidClseDt")

    @property
    def opening_dt(self) -> str:
        return self._get("opengDt")

    @property
    def amount(self) -> str:
        return self._get("asignBdgtAmt", "presmptPrce")

    @property
    def url(self) -> str:
        return self._get("bidNtceDtlUrl", "bidNtceUrl")


def _date_range(lookback_hours: int) -> tuple[str, str]:
    """inqryBgnDt / inqryEndDt 를 'YYYYMMDDHHMM' (KST) 형식으로 만든다."""
    now = datetime.now(KST)
    begin = now - timedelta(hours=lookback_hours)
    fmt = "%Y%m%d%H%M"
    return begin.strftime(fmt), now.strftime(fmt)


def _extract_items(payload: dict[str, Any]) -> tuple[list[dict], int]:
    """JSON 응답에서 items 리스트와 totalCount 를 안전하게 추출한다."""
    response = payload.get("response", payload)
    header = response.get("header", {})
    result_code = str(header.get("resultCode", ""))
    # '00' 또는 '0' 이 정상. 그 외에는 메시지를 올려 예외 처리.
    if result_code and result_code not in ("00", "0"):
        raise RuntimeError(
            f"API 오류 resultCode={result_code} msg={header.get('resultMsg')}"
        )

    body = response.get("body", {})
    items = body.get("items", [])
    # type=json 이면 보통 리스트, 간혹 {'item': [...]} 또는 단일 dict 로 온다.
    if isinstance(items, dict):
        items = items.get("item", [])
    if isinstance(items, dict):
        items = [items]
    if not isinstance(items, list):
        items = []

    try:
        total = int(body.get("totalCount", len(items)))
    except (TypeError, ValueError):
        total = len(items)
    return items, total


def fetch_operation(
    session: requests.Session,
    api_base: str,
    operation: str,
    service_key: str,
    begin_dt: str,
    end_dt: str,
    num_of_rows: int,
    max_pages: int,
    timeout: int,
) -> list[Bid]:
    """한 operation(물품/용역/공사)에 대해 기간 내 공고를 페이지네이션하며 모두 수집."""
    url = f"{api_base}/{operation}"
    collected: list[Bid] = []
    page = 1
    while page <= max_pages:
        params = {
            "serviceKey": service_key,
            "pageNo": page,
            "numOfRows": num_of_rows,
            "inqryDiv": 1,  # 1 = 공고게시일시 기준 조회
            "inqryBgnDt": begin_dt,
            "inqryEndDt": end_dt,
            "type": "json",
        }
        resp = session.get(url, params=params, timeout=timeout)
        resp.raise_for_status()
        try:
            payload = resp.json()
        except ValueError as exc:
            # 키 오류 등으로 XML(에러) 가 오면 본문 일부를 로그로 남긴다.
            raise RuntimeError(
                f"JSON 파싱 실패 ({operation}). 응답 일부: {resp.text[:300]}"
            ) from exc

        items, total = _extract_items(payload)
        collected.extend(Bid(item) for item in items)
        logger.info(
            "%s page=%d 수집=%d 누적=%d total=%d",
            operation, page, len(items), len(collected), total,
        )

        if not items or len(collected) >= total:
            break
        page += 1
    else:
        logger.warning(
            "%s: max_pages(%d) 도달 — 일부 공고를 놓쳤을 수 있습니다.",
            operation, max_pages,
        )
    return collected


def keyword_match(bid: Bid, keywords: Iterable[str]) -> str | None:
    """공고명에 키워드가 있으면 매칭된 키워드를 반환, 없으면 None."""
    name = bid.name.lower()
    for kw in keywords:
        if kw.lower() in name:
            return kw
    return None


def find_matching_bids(config) -> list[tuple[Bid, str]]:
    """설정된 모든 operation 을 조회해 키워드에 매칭되는 (공고, 키워드) 목록 반환."""
    begin_dt, end_dt = _date_range(config.lookback_hours)
    logger.info("조회 기간 %s ~ %s (KST)", begin_dt, end_dt)

    matches: list[tuple[Bid, str]] = []
    with requests.Session() as session:
        for operation in config.operations:
            try:
                bids = fetch_operation(
                    session=session,
                    api_base=config.api_base,
                    operation=operation,
                    service_key=config.service_key,
                    begin_dt=begin_dt,
                    end_dt=end_dt,
                    num_of_rows=config.num_of_rows,
                    max_pages=config.max_pages,
                    timeout=config.request_timeout,
                )
            except Exception:  # noqa: BLE001 - 한 operation 실패가 전체를 막지 않도록
                logger.exception("operation 조회 실패: %s", operation)
                continue

            for bid in bids:
                matched = keyword_match(bid, config.keywords)
                if matched:
                    matches.append((bid, matched))
    return matches
