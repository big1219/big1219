"""엔트리포인트: 나라장터 조회 → 신규 매칭 공고만 텔레그램 알림."""

from __future__ import annotations

import logging
import sys

from . import api, notifier, state
from .config import Config


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def run(config: Config) -> int:
    seen = state.load_seen(config.state_file)
    logger.info("기존 알림 기록 %d건 로드", len(seen))

    matches = api.find_matching_bids(config)
    logger.info("키워드 매칭 공고 %d건", len(matches))

    new_count = 0
    failed = 0
    for bid, keyword in matches:
        if bid.key in seen:
            continue
        message = notifier.build_message(bid, keyword)
        if config.dry_run:
            logger.info("[DRY_RUN] 전송 생략:\n%s\n", message)
            seen.add(bid.key)
            new_count += 1
            continue
        try:
            notifier.send_telegram(
                config.telegram_bot_token,
                config.telegram_chat_id,
                message,
                timeout=config.request_timeout,
            )
        except Exception:  # noqa: BLE001 - 한 건 실패가 나머지를 막지 않도록
            logger.exception("알림 전송 실패: %s", bid.key)
            failed += 1
            continue
        seen.add(bid.key)
        new_count += 1
        logger.info("알림 전송: %s | %s", bid.key, bid.name)

    state.save_seen(config.state_file, seen)
    logger.info("완료 — 신규 알림 %d건, 실패 %d건", new_count, failed)
    return 0 if failed == 0 else 1


logger = logging.getLogger("nara_monitor")


def main() -> int:
    configure_logging()
    config = Config.from_env()
    return run(config)


if __name__ == "__main__":
    sys.exit(main())
