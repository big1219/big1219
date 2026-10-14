"""리그 현황을 정적 HTML 대시보드로 렌더링한다.

생성된 파일(docs/index.html)을 GitHub Pages 로 서빙하면
전 지점이 같은 링크로 실시간 순위를 본다. 외부 라이브러리 없이 단일 파일로 만든다.
"""

from __future__ import annotations

import html
from datetime import datetime

from .league import KST, LeagueConfig, Standing

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def _fmt(value: float) -> str:
    """1234.0 → "1,234", 12.5 → "12.5"."""
    if value == int(value):
        return f"{int(value):,}"
    return f"{value:,.1f}"


def _season_label(season: str) -> str:
    year, month = season.split("-")
    return f"{year}년 {int(month)}월"


def render_dashboard(
    standings: list[Standing],
    config: LeagueConfig,
    season: str,
    generated_at: datetime | None = None,
) -> str:
    e = html.escape
    unit = e(config.unit)
    generated_at = generated_at or datetime.now(KST)
    updated = generated_at.astimezone(KST).strftime("%Y-%m-%d %H:%M")

    total_all = sum(s.total for s in standings)
    active = sum(1 for s in standings if s.total > 0)
    achievers = sum(1 for s in standings if s.achieved)
    leader = standings[0] if standings and standings[0].total > 0 else None

    top_tier = config.tiers[-1].liters if config.tiers else 0.0
    top_total = max((s.total for s in standings), default=0.0)
    scale_max = max(top_tier, top_total) * 1.06 or 1.0

    tier_marks = "".join(
        f'<div class="tier-mark" style="left:{t.liters / scale_max * 100:.2f}%">'
        f'<span>{e(t.name)} {_fmt(t.liters)}{unit}</span></div>'
        for t in config.tiers
    )

    rows = []
    for s in standings:
        width = s.total / scale_max * 100
        medal = MEDALS.get(s.rank, "")
        badges = "".join(
            f'<span class="badge">✓ {e(t.name)}</span>' for t in s.achieved
        )
        if s.next_tier:
            next_txt = f"{e(s.next_tier.name)}까지 {_fmt(s.remaining_to_next)}{unit}"
        elif s.achieved:
            next_txt = "전 티어 달성!"
        else:
            next_txt = ""
        rows.append(
            f'''<div class="row" data-branch="{e(s.branch)}" data-total="{_fmt(s.total)}{unit}"
     data-tiers="{e(', '.join(t.name for t in s.achieved) or '없음')}" data-next="{next_txt or '-'}">
  <div class="rank">{medal or s.rank}</div>
  <div class="who"><span class="name">{e(s.branch)}</span>{badges}</div>
  <div class="track">
    <div class="bar" style="width:{width:.2f}%"></div>
    <span class="val">{_fmt(s.total)}{unit}</span>
  </div>
  <div class="next">{next_txt}</div>
</div>'''
        )

    tier_rows = "".join(
        f"<tr><td>{e(t.name)}</td><td>{_fmt(t.liters)}{unit} 이상</td><td>{e(t.reward)}</td>"
        f"<td>{', '.join(e(s.branch) for s in standings if t in s.achieved) or '-'}</td></tr>"
        for t in config.tiers
    )

    leader_txt = e(leader.branch) if leader else "-"

    return f'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>{e(config.title)} — {_season_label(season)}</title>
<style>
  :root {{
    color-scheme: light;
    --page: #f9f9f7; --surface: #fcfcfb;
    --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --grid: #e1e0d9; --baseline: #c3c2b7;
    --series: #2a78d6; --good: #0ca30c; --good-text: #006300;
    --ring: rgba(11,11,11,0.10);
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      color-scheme: dark;
      --page: #0d0d0d; --surface: #1a1a19;
      --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --grid: #2c2c2a; --baseline: #383835;
      --series: #3987e5; --good: #0ca30c; --good-text: #0ca30c;
      --ring: rgba(255,255,255,0.10);
    }}
  }}
  :root[data-theme="dark"] {{
    color-scheme: dark;
    --page: #0d0d0d; --surface: #1a1a19;
    --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --baseline: #383835;
    --series: #3987e5; --good: #0ca30c; --good-text: #0ca30c;
    --ring: rgba(255,255,255,0.10);
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; background: var(--page); color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 880px; margin: 0 auto; padding: 24px 16px 48px; }}
  header h1 {{ font-size: 22px; margin: 0; }}
  header .sub {{ color: var(--ink-2); font-size: 14px; margin-top: 4px; }}
  .kpis {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; margin: 20px 0; }}
  .kpi {{ background: var(--surface); border: 1px solid var(--ring); border-radius: 10px; padding: 12px 14px; }}
  .kpi .label {{ font-size: 12px; color: var(--ink-2); }}
  .kpi .value {{ font-size: 26px; font-weight: 700; margin-top: 2px; }}
  .kpi .value small {{ font-size: 14px; font-weight: 500; color: var(--ink-2); }}
  section.board {{ background: var(--surface); border: 1px solid var(--ring); border-radius: 10px; padding: 18px 16px 8px; }}
  section.board h2, section.tiers h2 {{ font-size: 15px; margin: 0 0 12px; }}
  .axis {{ position: relative; height: 26px; margin-left: var(--indent); margin-right: var(--rpad); }}
  .tier-mark {{ position: absolute; top: 0; bottom: -9999px; border-left: 1px dashed var(--grid); pointer-events: none; }}
  .tier-mark span {{ position: absolute; top: 0; left: 4px; font-size: 11px; color: var(--muted); white-space: nowrap; }}
  .axis, .rows {{ --indent: 224px; --rpad: 76px; }}
  .rows {{ position: relative; overflow: hidden; }}
  .row {{ display: grid; grid-template-columns: 34px 172px 1fr; gap: 8px; align-items: center; padding: 9px 0; border-top: 1px solid var(--grid); }}
  .row:first-child {{ border-top: none; }}
  .rank {{ font-size: 16px; text-align: center; color: var(--ink-2); font-variant-numeric: tabular-nums; }}
  .who {{ min-width: 0; }}
  .who .name {{ font-weight: 600; font-size: 14px; }}
  .badge {{ display: inline-block; margin-left: 6px; font-size: 11px; color: var(--good-text); border: 1px solid var(--good); border-radius: 999px; padding: 0 7px; white-space: nowrap; }}
  .track {{ position: relative; height: 20px; border-left: 2px solid var(--baseline); padding-right: var(--rpad); }}
  .bar {{ height: 14px; margin-top: 3px; background: var(--series); border-radius: 0 4px 4px 0; min-width: 2px; }}
  .val {{ position: absolute; right: 0; top: 0; font-size: 13px; font-variant-numeric: tabular-nums; color: var(--ink); }}
  .next {{ grid-column: 3; font-size: 12px; color: var(--ink-2); margin-top: -4px; }}
  section.tiers {{ margin-top: 20px; }}
  table {{ width: 100%; border-collapse: collapse; background: var(--surface); border: 1px solid var(--ring); border-radius: 10px; overflow: hidden; font-size: 13px; }}
  th, td {{ text-align: left; padding: 9px 12px; border-top: 1px solid var(--grid); }}
  thead th {{ border-top: none; color: var(--ink-2); font-weight: 600; font-size: 12px; }}
  footer {{ color: var(--muted); font-size: 12px; margin-top: 20px; }}
  #tip {{ position: fixed; display: none; background: var(--surface); border: 1px solid var(--ring); border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.15); pointer-events: none; z-index: 9; max-width: 240px; }}
  #tip b {{ display: block; font-size: 13px; }}
  @media (max-width: 560px) {{
    .row {{ grid-template-columns: 26px 1fr; }}
    .track {{ grid-column: 1 / -1; margin-left: 34px; }}
    .next {{ grid-column: 1 / -1; margin-left: 34px; }}
    .axis, .rows {{ --indent: 36px; }}
    .axis {{ height: 8px; }}
    .tier-mark span {{ display: none; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>🛢️ {e(config.title)}</h1>
    <div class="sub">{_season_label(season)} 시즌 · 지점별 엔진오일 소모량 리더보드 · {updated} 기준 (5분마다 자동 새로고침)</div>
  </header>

  <div class="kpis">
    <div class="kpi"><div class="label">이번 달 전체 소모량</div><div class="value">{_fmt(total_all)}<small> {unit}</small></div></div>
    <div class="kpi"><div class="label">현재 1위</div><div class="value">{leader_txt}</div></div>
    <div class="kpi"><div class="label">기록 지점</div><div class="value">{active}<small> / {len(standings)}</small></div></div>
    <div class="kpi"><div class="label">티어 달성 지점</div><div class="value">{achievers}<small> 곳</small></div></div>
  </div>

  <section class="board">
    <h2>지점 순위</h2>
    <div class="rows">
      <div class="axis">{tier_marks}</div>
      {"".join(rows)}
    </div>
  </section>

  <section class="tiers">
    <h2>🎁 리워드 티어 안내</h2>
    <table>
      <thead><tr><th>티어</th><th>기준(시즌 누적)</th><th>보상</th><th>달성 지점</th></tr></thead>
      <tbody>{tier_rows}</tbody>
    </table>
  </section>

  <footer>기록이 등록되면 자동으로 갱신됩니다 · 시즌은 매월 1일 초기화 · {e(config.brand)}</footer>
</div>

<div id="tip"></div>
<script>
  const tip = document.getElementById("tip");
  document.querySelectorAll(".row").forEach(row => {{
    row.addEventListener("pointermove", ev => {{
      tip.innerHTML = "<b>" + row.dataset.branch + "</b>"
        + "누적 " + row.dataset.total
        + "<br>달성 티어: " + row.dataset.tiers
        + "<br>다음 목표: " + row.dataset.next;
      tip.style.display = "block";
      const x = Math.min(ev.clientX + 12, window.innerWidth - tip.offsetWidth - 8);
      tip.style.left = x + "px";
      tip.style.top = (ev.clientY + 14) + "px";
    }});
    row.addEventListener("pointerleave", () => tip.style.display = "none");
  }});
</script>
</body>
</html>
'''
