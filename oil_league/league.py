"""지점별 엔진오일 소모량 집계 · 랭킹 · 리워드 티어 판정.

data/oil_usage.csv 에 쌓인 사용 기록을 시즌(월) 단위로 집계해서
지점별 순위와 티어 달성 현황을 계산한다.
"""

from __future__ import annotations

import csv
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))


@dataclass(frozen=True)
class Tier:
    """리워드 티어. liters 이상 소모하면 reward 지급 대상."""

    name: str
    liters: float
    reward: str


@dataclass
class LeagueConfig:
    brand: str
    title: str
    unit: str
    tiers: list[Tier]          # liters 오름차순 정렬 보장
    branches: list[str]        # 로스터(0L 지점도 보드에 표시)
    season: str | None = None  # "YYYY-MM", None 이면 이번 달(KST)


@dataclass
class Standing:
    """한 지점의 시즌 성적."""

    branch: str
    total: float
    rank: int = 0
    achieved: list[Tier] = field(default_factory=list)
    next_tier: Tier | None = None

    @property
    def remaining_to_next(self) -> float:
        if self.next_tier is None:
            return 0.0
        return max(0.0, self.next_tier.liters - self.total)


def current_season(now: datetime | None = None) -> str:
    """KST 기준 이번 달을 "YYYY-MM" 으로 반환."""
    now = now or datetime.now(KST)
    return now.astimezone(KST).strftime("%Y-%m")


def load_league_config(path: str) -> LeagueConfig:
    with open(path, "r", encoding="utf-8") as fp:
        raw = json.load(fp)
    tiers = sorted(
        (Tier(t["name"], float(t["liters"]), t.get("reward", "")) for t in raw.get("tiers", [])),
        key=lambda t: t.liters,
    )
    return LeagueConfig(
        brand=raw.get("brand", "Truck Care"),
        title=raw.get("title", "엔진오일 리그"),
        unit=raw.get("unit", "L"),
        tiers=tiers,
        branches=list(raw.get("branches", [])),
        season=raw.get("season") or None,
    )


def load_entries(path: str) -> list[tuple[str, str, float]]:
    """CSV에서 (날짜 "YYYY-MM-DD", 지점명, 리터) 목록을 읽는다. 잘못된 행은 건너뛴다."""
    entries: list[tuple[str, str, float]] = []
    with open(path, "r", encoding="utf-8") as fp:
        for lineno, row in enumerate(csv.DictReader(fp), start=2):
            date = (row.get("date") or "").strip()
            branch = (row.get("branch") or "").strip()
            try:
                liters = float((row.get("liters") or "").strip())
            except ValueError:
                logger.warning("liters 파싱 실패 — %d행 건너뜀: %r", lineno, row)
                continue
            if not date or not branch or liters < 0:
                logger.warning("잘못된 행 — %d행 건너뜀: %r", lineno, row)
                continue
            entries.append((date, branch, liters))
    return entries


def compute_standings(
    entries: list[tuple[str, str, float]],
    config: LeagueConfig,
    season: str,
) -> list[Standing]:
    """시즌(YYYY-MM) 기록만 집계해 소모량 내림차순 순위를 매긴다.

    동점이면 같은 순위(1224식). 로스터에 있는 지점은 기록이 없어도 0L로 표시하고,
    로스터에 없어도 기록이 있으면 보드에 올린다.
    """
    totals: dict[str, float] = {name: 0.0 for name in config.branches}
    for date, branch, liters in entries:
        if not date.startswith(season):
            continue
        totals[branch] = totals.get(branch, 0.0) + liters

    standings = [Standing(branch=name, total=total) for name, total in totals.items()]
    standings.sort(key=lambda s: (-s.total, s.branch))

    prev_total: float | None = None
    prev_rank = 0
    for idx, standing in enumerate(standings, start=1):
        if standing.total == prev_total:
            standing.rank = prev_rank
        else:
            standing.rank = idx
            prev_total, prev_rank = standing.total, idx
        standing.achieved = [t for t in config.tiers if standing.total >= t.liters]
        standing.next_tier = next((t for t in config.tiers if standing.total < t.liters), None)
    return standings


def new_achievements(
    standings: list[Standing],
    season: str,
    awarded_keys: set[str],
) -> list[tuple[Standing, Tier]]:
    """아직 알림을 보내지 않은 (지점, 티어) 달성 건을 낮은 티어부터 반환."""
    fresh: list[tuple[Standing, Tier]] = []
    for standing in standings:
        for tier in standing.achieved:
            if award_key(season, standing.branch, tier) not in awarded_keys:
                fresh.append((standing, tier))
    return fresh


def award_key(season: str, branch: str, tier: Tier) -> str:
    return f"{season}::{branch}::{tier.name}"
