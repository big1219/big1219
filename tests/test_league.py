import json

from oil_league import league


def make_config(tmp_path, **overrides):
    raw = {
        "brand": "Truck Care",
        "title": "Truck Care 엔진오일 리그",
        "unit": "L",
        "tiers": [
            {"name": "실버", "liters": 600, "reward": "상품권 10만원"},
            {"name": "브론즈", "liters": 300, "reward": "상품권 3만원"},
        ],
        "branches": ["성수점", "부천점", "김해점"],
    }
    raw.update(overrides)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    return league.load_league_config(str(path))


def test_config_tiers_sorted_ascending(tmp_path):
    config = make_config(tmp_path)
    assert [t.name for t in config.tiers] == ["브론즈", "실버"]


def test_standings_filters_season_and_ranks(tmp_path):
    config = make_config(tmp_path)
    entries = [
        ("2026-08-01", "성수점", 200.0),
        ("2026-08-02", "성수점", 120.0),
        ("2026-08-01", "부천점", 350.0),
        ("2026-07-31", "부천점", 999.0),  # 지난 시즌 — 제외
        ("2026-08-03", "신규점", 100.0),  # 로스터 밖 지점도 집계
    ]
    standings = league.compute_standings(entries, config, "2026-08")
    by_name = {s.branch: s for s in standings}

    assert by_name["성수점"].total == 320.0
    assert by_name["부천점"].total == 350.0
    assert by_name["부천점"].rank == 1
    assert by_name["성수점"].rank == 2
    assert by_name["신규점"].total == 100.0
    assert by_name["김해점"].total == 0.0  # 기록 없어도 보드에 표시


def test_tie_gets_same_rank(tmp_path):
    config = make_config(tmp_path, branches=["A", "B", "C"])
    entries = [
        ("2026-08-01", "A", 100.0),
        ("2026-08-01", "B", 100.0),
        ("2026-08-01", "C", 50.0),
    ]
    standings = league.compute_standings(entries, config, "2026-08")
    ranks = {s.branch: s.rank for s in standings}
    assert ranks["A"] == 1 and ranks["B"] == 1
    assert ranks["C"] == 3  # 1224식


def test_tier_achievement_and_next(tmp_path):
    config = make_config(tmp_path)
    entries = [("2026-08-01", "성수점", 450.0)]
    standings = league.compute_standings(entries, config, "2026-08")
    s = next(x for x in standings if x.branch == "성수점")

    assert [t.name for t in s.achieved] == ["브론즈"]
    assert s.next_tier.name == "실버"
    assert s.remaining_to_next == 150.0


def test_new_achievements_skips_already_awarded(tmp_path):
    config = make_config(tmp_path)
    entries = [("2026-08-01", "성수점", 700.0)]
    standings = league.compute_standings(entries, config, "2026-08")
    bronze, silver = config.tiers

    awarded = {league.award_key("2026-08", "성수점", bronze)}
    fresh = league.new_achievements(standings, "2026-08", awarded)
    assert [(s.branch, t.name) for s, t in fresh] == [("성수점", "실버")]

    # 시즌이 바뀌면 같은 티어도 다시 알림 대상
    fresh_new_season = league.new_achievements(standings, "2026-09", awarded)
    assert len(fresh_new_season) == 2


def test_load_entries_skips_bad_rows(tmp_path):
    path = tmp_path / "usage.csv"
    path.write_text(
        "date,branch,liters,memo\n"
        "2026-08-01,성수점,86,정상\n"
        "2026-08-01,,50,지점 누락\n"
        "2026-08-02,부천점,abc,숫자 아님\n"
        "2026-08-03,부천점,-5,음수\n",
        encoding="utf-8",
    )
    entries = league.load_entries(str(path))
    assert entries == [("2026-08-01", "성수점", 86.0)]
