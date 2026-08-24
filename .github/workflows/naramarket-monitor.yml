#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""원격 seen.json 과 이번 실행 결과를 '합집합'으로 병합해 저장한다.

push 경합(remote가 앞서 있어 reject)이 나서 재시도할 때, 원격 기록과 로컬 기록
어느 쪽도 잃지 않도록 두 seen 목록을 union 한다. 저장 형식은 nara_monitor/state.py
와 동일하게 맞춘다({updated_at, count, seen}).

usage: python scripts/merge_seen.py <remote_seen_path> <local_seen_path> <out_path>
  - remote_seen_path: 최신 원격 main 의 state/seen.json (기준선)
  - local_seen_path : 이번 실행이 만든 seen.json 사본
  - out_path        : 병합 결과를 쓸 경로(보통 remote_seen_path 와 동일)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def load_keys(path: str) -> list[str]:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if isinstance(data, dict):
        return list(data.get("seen", []))
    if isinstance(data, list):
        return list(data)
    return []


def main() -> int:
    if len(sys.argv) != 4:
        print("usage: merge_seen.py <remote> <local> <out>", file=sys.stderr)
        return 2
    remote_path, local_path, out_path = sys.argv[1], sys.argv[2], sys.argv[3]
    merged = sorted(set(load_keys(remote_path)) | set(load_keys(local_path)))
    payload = {
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "count": len(merged),
        "seen": merged,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"merged seen keys: {len(merged)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
