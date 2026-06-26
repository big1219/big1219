"""네트워크 없이 검증 가능한 순수 로직 테스트."""

from nara_monitor.api import Bid, _extract_items, keyword_match
from nara_monitor.notifier import build_message, _fmt_amount


def _bid(name: str) -> Bid:
    return Bid({"bidNtceNm": name, "bidNtceNo": "20240101", "bidNtceOrd": "00"})


def test_keyword_match_hit():
    assert keyword_match(_bid("디젤 엔진오일 구매"), ["엔진오일"]) == "엔진오일"


def test_keyword_match_case_insensitive():
    assert keyword_match(_bid("ENGINE OIL 구매"), ["engine oil"]) == "engine oil"


def test_keyword_match_miss():
    assert keyword_match(_bid("복사용지 구매"), ["엔진오일", "윤활유"]) is None


def test_extract_items_list_form():
    payload = {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {"items": [{"bidNtceNm": "a"}, {"bidNtceNm": "b"}], "totalCount": 2},
        }
    }
    items, total = _extract_items(payload)
    assert len(items) == 2 and total == 2


def test_extract_items_item_wrapped_form():
    payload = {
        "response": {
            "header": {"resultCode": "0"},
            "body": {"items": {"item": [{"bidNtceNm": "a"}]}, "totalCount": 1},
        }
    }
    items, total = _extract_items(payload)
    assert len(items) == 1 and total == 1


def test_extract_items_error_code_raises():
    payload = {"response": {"header": {"resultCode": "30", "resultMsg": "SERVICE KEY ERROR"}, "body": {}}}
    try:
        _extract_items(payload)
        assert False, "예외가 발생해야 함"
    except RuntimeError as exc:
        assert "30" in str(exc)


def test_bid_key():
    assert _bid("x").key == "20240101-00"


def test_fmt_amount():
    assert _fmt_amount("1234567") == "1,234,567원"
    assert _fmt_amount("") == "-"
    assert _fmt_amount("미정") == "미정"


def test_build_message_contains_essentials():
    bid = Bid(
        {
            "bidNtceNm": "디젤 엔진오일 구매",
            "bidNtceNo": "2024",
            "bidNtceOrd": "00",
            "ntceInsttNm": "조달청",
            "asignBdgtAmt": "5000000",
            "bidNtceDtlUrl": "https://example.com/notice",
        }
    )
    msg = build_message(bid, "엔진오일")
    assert "디젤 엔진오일 구매" in msg
    assert "조달청" in msg
    assert "5,000,000원" in msg
    assert "https://example.com/notice" in msg
