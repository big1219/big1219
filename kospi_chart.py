#!/usr/bin/env python3
"""코스피(KOSPI) 지수 차트 + 10일 이동평균선 생성기.

코스피 종가를 받아와서 종가 선과 10일 단순이동평균선(SMA10)을 한 차트에
그린 뒤 PNG로 저장한다. 데이터 소스는 아래 순서로 자동 폴백한다.

    1) FinanceDataReader  (pip install finance-datareader)
    2) yfinance           (pip install yfinance, 티커 ^KS11)
    3) stooq CSV          (requests 로 https://stooq.com/q/d/l 직접 호출)

사용 예:
    pip install matplotlib pandas finance-datareader   # 또는 yfinance
    python kospi_chart.py                  # 최근 6개월, kospi_ma10.png 저장
    python kospi_chart.py --period 1y --ma 10 --out chart.png

주의: 실시간 시세를 받으려면 네트워크 접근이 필요하다. 사내/샌드박스
프록시가 금융 사이트를 차단하면 데이터 조회 단계에서 실패한다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sys

logger = logging.getLogger("kospi_chart")

TELEGRAM_PHOTO_API = "https://api.telegram.org/bot{token}/sendPhoto"


def _start_date(period: str) -> dt.date:
    """'6mo' / '1y' / '3mo' 같은 기간 문자열을 시작일로 변환."""
    today = dt.date.today()
    p = period.lower().strip()
    if p.endswith("mo"):
        return today - dt.timedelta(days=31 * int(p[:-2]))
    if p.endswith("y"):
        return today - dt.timedelta(days=365 * int(p[:-1]))
    if p.endswith("m"):
        return today - dt.timedelta(days=31 * int(p[:-1]))
    if p.endswith("d"):
        return today - dt.timedelta(days=int(p[:-1]))
    raise ValueError(f"알 수 없는 기간 형식: {period!r} (예: 3mo, 6mo, 1y)")


def fetch_via_fdr(start: dt.date):
    """FinanceDataReader 로 코스피(KS11) 일봉을 가져온다."""
    import FinanceDataReader as fdr  # type: ignore

    df = fdr.DataReader("KS11", start.isoformat())
    return df["Close"].rename("Close")


def fetch_via_yfinance(start: dt.date):
    """yfinance 로 코스피(^KS11) 일봉을 가져온다."""
    import yfinance as yf  # type: ignore

    df = yf.download("^KS11", start=start.isoformat(), progress=False)
    close = df["Close"]
    # yfinance 가 멀티컬럼을 줄 때가 있어 1차원으로 정리
    if hasattr(close, "columns"):
        close = close.iloc[:, 0]
    return close.rename("Close")


def fetch_via_stooq(start: dt.date):
    """stooq CSV 에서 코스피(^kospi) 일봉을 가져온다."""
    import io

    import pandas as pd
    import requests

    url = "https://stooq.com/q/d/l/?s=^kospi&i=d"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    df = pd.read_csv(io.StringIO(resp.text), parse_dates=["Date"]).set_index("Date")
    df = df[df.index.date >= start]
    return df["Close"].rename("Close")


_SOURCES = [
    ("FinanceDataReader", fetch_via_fdr),
    ("yfinance", fetch_via_yfinance),
    ("stooq", fetch_via_stooq),
]


def load_kospi(start: dt.date):
    """사용 가능한 소스를 순서대로 시도해 코스피 종가 시리즈를 반환."""
    errors = []
    for name, fn in _SOURCES:
        try:
            series = fn(start)
            if series is not None and len(series.dropna()) > 0:
                logger.info("데이터 소스: %s (%d 거래일)", name, len(series.dropna()))
                return series.dropna()
            errors.append(f"{name}: 빈 결과")
        except ImportError as exc:
            errors.append(f"{name}: 미설치 ({exc.name})")
        except Exception as exc:  # noqa: BLE001 - 소스별로 다양한 예외
            errors.append(f"{name}: {type(exc).__name__}: {exc}")
    raise RuntimeError("모든 데이터 소스 실패:\n  - " + "\n  - ".join(errors))


def make_chart(close, ma_window: int, out_path: str) -> None:
    """종가 + N일 이동평균선 차트를 그려 PNG로 저장."""
    import matplotlib

    matplotlib.use("Agg")  # 화면 없는 환경에서도 저장되도록
    import matplotlib.pyplot as plt

    ma = close.rolling(window=ma_window).mean()

    fig, ax = plt.subplots(figsize=(12, 6))
    ax.plot(close.index, close.values, label="코스피 종가", color="#1f77b4", linewidth=1.3)
    ax.plot(ma.index, ma.values, label=f"{ma_window}일 이동평균", color="#d62728", linewidth=1.8)

    last_date = close.index[-1]
    last_close = float(close.iloc[-1])
    ax.set_title(
        f"코스피(KOSPI) 지수 — {ma_window}일 이동평균선  "
        f"(최근 종가 {last_close:,.2f}, {last_date:%Y-%m-%d})"
    )
    ax.set_xlabel("날짜")
    ax.set_ylabel("지수")
    ax.legend(loc="best")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=130)
    plt.close(fig)
    logger.info("차트 저장 완료: %s", out_path)


def build_caption(close, ma_window: int) -> str:
    """텔레그램 사진 캡션(HTML): 종가·전일대비·이동평균 이격."""
    last_date = close.index[-1]
    last_close = float(close.iloc[-1])

    ma = close.rolling(window=ma_window).mean()
    last_ma = ma.iloc[-1]
    if last_ma == last_ma:  # NaN 아님
        last_ma = float(last_ma)
        gap_pct = (last_close - last_ma) / last_ma * 100
        side = "위 ▲" if last_close >= last_ma else "아래 ▼"
        ma_line = f"📏 {ma_window}일 이평: {last_ma:,.2f} (종가가 {abs(gap_pct):.2f}% {side})"
    else:
        ma_line = f"📏 {ma_window}일 이평: 데이터 부족"

    if len(close) >= 2:
        prev = float(close.iloc[-2])
        chg = last_close - prev
        chg_pct = (chg / prev * 100) if prev else 0.0
        arrow = "🔺" if chg > 0 else ("🔻" if chg < 0 else "▶")
        chg_line = f"💹 종가 <b>{last_close:,.2f}</b> {arrow} {chg:+,.2f} ({chg_pct:+.2f}%)"
    else:
        chg_line = f"💹 종가 <b>{last_close:,.2f}</b>"

    return (
        f"📈 <b>코스피(KOSPI) {ma_window}일 이평선</b>\n"
        f"🗓 {last_date:%Y-%m-%d}\n"
        f"{chg_line}\n"
        f"{ma_line}"
    )


def send_telegram_photo(token: str, chat_id: str, photo_path: str, caption: str,
                        timeout: int = 60) -> None:
    """텔레그램으로 차트 PNG를 전송."""
    import requests

    with open(photo_path, "rb") as fp:
        resp = requests.post(
            TELEGRAM_PHOTO_API.format(token=token),
            data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
            files={"photo": fp},
            timeout=timeout,
        )
    if resp.status_code != 200:
        raise RuntimeError(
            f"텔레그램 사진 전송 실패 status={resp.status_code} body={resp.text[:300]}"
        )
    logger.info("텔레그램 전송 완료 (chat_id=%s)", chat_id)


def _try_set_korean_font() -> None:
    """한글 폰트가 있으면 적용(없으면 무시 — 라벨이 깨질 수 있음)."""
    try:
        import matplotlib
        from matplotlib import font_manager

        for name in ("NanumGothic", "Malgun Gothic", "AppleGothic", "Noto Sans CJK KR"):
            if any(name in f.name for f in font_manager.fontManager.ttflist):
                matplotlib.rcParams["font.family"] = name
                break
        matplotlib.rcParams["axes.unicode_minus"] = False
    except Exception:  # noqa: BLE001
        pass


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="코스피 지수 + 이동평균선 차트 생성")
    parser.add_argument("--period", default="6mo", help="조회 기간 (예: 3mo, 6mo, 1y). 기본 6mo")
    parser.add_argument("--ma", type=int, default=10, help="이동평균 일수. 기본 10")
    parser.add_argument("--out", default="kospi_ma10.png", help="저장할 PNG 경로")
    parser.add_argument(
        "--send",
        action="store_true",
        help="차트를 텔레그램으로 전송 (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 환경변수 필요)",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    _try_set_korean_font()

    start = _start_date(args.period)
    try:
        close = load_kospi(start)
    except RuntimeError as exc:
        logger.error("%s", exc)
        logger.error(
            "\n네트워크/데이터 소스 접근이 막혀 있을 수 있습니다. "
            "인터넷이 되는 환경에서 다음 중 하나를 설치 후 다시 실행하세요:\n"
            "  pip install finance-datareader   # 또는\n"
            "  pip install yfinance"
        )
        return 1

    if len(close) < args.ma:
        logger.warning("거래일이 %d개뿐이라 %d일 이동평균이 일부만 계산됩니다.", len(close), args.ma)

    make_chart(close, args.ma, args.out)

    if args.send:
        # 코스피 전용 설정이 있으면 우선 사용, 없으면 나라장터 봇 설정으로 폴백.
        # → KOSPI_CHAT_ID 만 따로 등록하면 같은 봇으로 별도 방에 보낼 수 있다.
        token = os.environ.get("KOSPI_BOT_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
        chat_id = os.environ.get("KOSPI_CHAT_ID") or os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not chat_id:
            logger.error(
                "텔레그램 전송에는 봇 토큰과 chat_id 가 필요합니다.\n"
                "  토큰  : KOSPI_BOT_TOKEN(전용) 또는 TELEGRAM_BOT_TOKEN\n"
                "  chat : KOSPI_CHAT_ID(전용) 또는 TELEGRAM_CHAT_ID"
            )
            return 1
        send_telegram_photo(token, chat_id, args.out, build_caption(close, args.ma))

    return 0


if __name__ == "__main__":
    sys.exit(main())
