"""엔트리포인트: 소모량 집계 → 대시보드(HTML) 생성 → 신규 티어 달성 텔레그램 알림.

텔레그램 설정(TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)이 없으면
알림은 건너뛰고 대시보드만 생성한다.
"""

from __future__ import annotations

import html
import json
import logging
import os
import sys
from datetime import datetime, timezone

from nara_monitor.notifier import send_telegram

from . import league
from .dashboard import render_dashboard
from .league import Standing, Tier

logger = logging.getLogger("oil_league")

CONFIG_FILE = os.environ.get("LEAGUE_CONFIG_FILE", "data/league_config.json")
USAGE_FILE = os.environ.get("LEAGUE_USAGE_FILE", "data/oil_usage.csv")
OUTPUT_FILE = os.environ.get("LEAGUE_OUTPUT_FILE", "docs/index.html")
AWARDS_FILE = os.environ.get("LEAGUE_AWARDS_FILE", "state/oil_awards.json")


def load_awards(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        logger.warning("어워드 기록을 읽지 못해 빈 상태로 시작합니다: %s", path)
        return set()
    return set(data.get("awarded", []))


def save_awards(path: str, awarded: set[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(awarded),
        "awarded": sorted(awarded),
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def build_award_message(standing: Standing, tier: Tier, season: str, unit: str) -> str:
    e = html.escape
    lines = [
        "🏆 <b>엔진오일 리그 티어 달성!</b>",
        "",
        f"🏪 지점: <b>{e(standing.branch)}</b> (현재 {standing.rank}위)",
        f"🎖 달성 티어: <b>{e(tier.name)}</b> ({tier.liters:,.0f}{e(unit)} 이상)",
        f"🛢 시즌 누적: {standing.total:,.0f}{e(unit)} ({e(season)})",
        f"🎁 보상: <b>{e(tier.reward)}</b>",
        "",
        "다른 지점들도 조금만 더! 💪",
    ]
    return "\n".join(lines)


def run() -> int:
    config = league.load_league_config(CONFIG_FILE)
    season = config.season or league.current_season()
    entries = league.load_entries(USAGE_FILE)
    standings = league.compute_standings(entries, config, season)
    logger.info("시즌 %s — 기록 %d건, 지점 %d곳 집계", season, len(entries), len(standings))

    os.makedirs(os.path.dirname(OUTPUT_FILE) or ".", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as fp:
        fp.write(render_dashboard(standings, config, season))
    logger.info("대시보드 생성: %s", OUTPUT_FILE)

    awarded = load_awards(AWARDS_FILE)
    fresh = league.new_achievements(standings, season, awarded)
    if not fresh:
        logger.info("신규 티어 달성 없음")
        return 0

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    failed = 0
    for standing, tier in fresh:
        message = build_award_message(standing, tier, season, config.unit)
        key = league.award_key(season, standing.branch, tier)
        if dry_run or not (token and chat_id):
            logger.info("[전송 생략] %s\n%s\n", key, message)
            awarded.add(key)
            continue
        try:
            send_telegram(token, chat_id, message)
        except Exception:  # noqa: BLE001 - 한 건 실패가 나머지를 막지 않도록
            logger.exception("티어 달성 알림 실패: %s", key)
            failed += 1
            continue
        awarded.add(key)
        logger.info("티어 달성 알림 전송: %s", key)

    save_awards(AWARDS_FILE, awarded)
    logger.info("완료 — 신규 달성 %d건, 실패 %d건", len(fresh) - failed, failed)
    return 0 if failed == 0 else 1


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return run()


if __name__ == "__main__":
    sys.exit(main())
