"""이미 알림을 보낸 공고를 기록해 중복 알림을 막는다."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# 상태 파일이 무한정 커지지 않도록 보관할 최대 키 개수.
MAX_KEYS = 5000


def load_seen(path: str) -> set[str]:
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as fp:
            data = json.load(fp)
    except (json.JSONDecodeError, OSError):
        logger.warning("상태 파일을 읽지 못해 빈 상태로 시작합니다: %s", path)
        return set()
    keys = data.get("seen", []) if isinstance(data, dict) else data
    return set(keys)


def save_seen(path: str, seen: set[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    # 키가 너무 많아지면 최근 것 위주로 유지(정렬 후 잘라냄).
    keys = sorted(seen)
    if len(keys) > MAX_KEYS:
        keys = keys[-MAX_KEYS:]
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(keys),
        "seen": keys,
    }
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)
