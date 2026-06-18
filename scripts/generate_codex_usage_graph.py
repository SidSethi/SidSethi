#!/usr/bin/env python3
"""Generate a GitHub-profile-safe Codex activity dashboard."""

from __future__ import annotations

import json
import math
import subprocess
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "assets" / "codex-usage.svg"

WIDTH = 840
HEIGHT = 500
MARGIN = 28

BG = "#0d1117"
PANEL = "#161b22"
PANEL_STROKE = "#30363d"
TEXT = "#f0f6fc"
MUTED = "#8b949e"
EMPTY = "#21262d"
GRID_COLORS = ["#26384c", "#315071", "#3f6f9f", "#69b7ff"]
FONT = "Arial, Helvetica, sans-serif"

CELL = 9
GAP = 4
GRID_COLUMNS = 53
GRID_ROWS = 7
GRID_X = MARGIN
GRID_Y = 214
GRID_WIDTH = (CELL * GRID_COLUMNS) + (GAP * (GRID_COLUMNS - 1))
GRID_HEIGHT = (CELL * GRID_ROWS) + (GAP * (GRID_ROWS - 1))


def run_codexbar() -> dict[str, Any]:
    result = subprocess.run(
        ["codexbar", "cost", "--provider", "codex", "--format", "json", "--refresh"],
        check=True,
        capture_output=True,
        text=True,
    )
    providers = json.loads(result.stdout)
    for provider in providers:
        if provider.get("provider") == "codex":
            return provider
    raise RuntimeError("CodexBar returned no codex provider data")


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def parse_updated_at(value: str | None, fallback: date) -> str:
    if not value:
        return fallback.strftime("%b %-d, %Y")
    normalized = value.replace("Z", "+00:00")
    try:
        updated = datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except ValueError:
        return fallback.strftime("%b %-d, %Y")
    return updated.strftime("%b %-d, %Y")


def short_number(value: int | float) -> str:
    rounded = int(round(value))
    units = [
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ]
    for size, suffix in units:
        if rounded >= size:
            number = rounded / size
            if number < 10:
                return f"{number:.2f}{suffix}"
            return f"{number:.1f}{suffix}"
    return str(rounded)


def daily_token_map(provider: dict[str, Any]) -> dict[date, int]:
    daily: dict[date, int] = {}
    for item in provider.get("daily", []):
        if not item.get("date"):
            continue
        day = parse_date(item["date"])
        daily[day] = int(item.get("totalTokens", 0))
    return daily


def current_streak(daily: dict[date, int], end: date) -> int:
    streak = 0
    cursor = end
    while daily.get(cursor, 0) > 0:
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(daily: dict[date, int]) -> int:
    if not daily:
        return 0
    longest = 0
    current = 0
    cursor = min(daily)
    end = max(daily)
    while cursor <= end:
        if daily.get(cursor, 0) > 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
        cursor += timedelta(days=1)
    return longest


def heat_color(tokens: int, max_tokens: int) -> str:
    if tokens <= 0 or max_tokens <= 0:
        return EMPTY
    ratio = math.log10(tokens + 1) / math.log10(max_tokens + 1)
    if ratio < 0.35:
        return GRID_COLORS[0]
    if ratio < 0.58:
        return GRID_COLORS[1]
    if ratio < 0.8:
        return GRID_COLORS[2]
    return GRID_COLORS[3]


def display_range(end: date) -> tuple[date, date]:
    # Sunday-start, Saturday-end, matching the shape of a GitHub-style grid.
    days_until_saturday = (5 - end.weekday()) % 7
    display_end = end + timedelta(days=days_until_saturday)
    display_start = display_end - timedelta(days=(GRID_COLUMNS * 7) - 1)
    return display_start, display_end


def render_metric(x: float, y: float, width: float, value: str, label: str) -> str:
    return f"""
  <g>
    <text x="{x + width / 2:.2f}" y="{y + 31}" fill="{TEXT}" font-family="{FONT}" font-size="20" text-anchor="middle">{escape(value)}</text>
    <text x="{x + width / 2:.2f}" y="{y + 55}" fill="{MUTED}" font-family="{FONT}" font-size="13" text-anchor="middle">{escape(label)}</text>
  </g>"""


def render_month_labels(start: date, end: date) -> str:
    labels: list[str] = []
    cursor = date(start.year, start.month, 1)
    if cursor < start:
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)

    while cursor <= end:
        column = (cursor - start).days // 7
        if 0 <= column < GRID_COLUMNS:
            x = GRID_X + column * (CELL + GAP)
            labels.append(
                f'<text x="{x}" y="{GRID_Y + GRID_HEIGHT + 30}" fill="{MUTED}" '
                f'font-family="{FONT}" '
                f'font-size="13">{escape(cursor.strftime("%b"))}</text>'
            )
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return "\n  ".join(labels)


def render_heatmap(daily: dict[date, int], start: date, end: date, data_end: date) -> str:
    max_tokens = max(daily.values()) if daily else 0
    cells: list[str] = []
    for column in range(GRID_COLUMNS):
        for row in range(GRID_ROWS):
            day = start + timedelta(days=(column * 7) + row)
            tokens = daily.get(day, 0) if day <= data_end else 0
            color = heat_color(tokens, max_tokens)
            x = GRID_X + column * (CELL + GAP)
            y = GRID_Y + row * (CELL + GAP)
            title = f"{day.isoformat()}: relative Codex activity"
            cells.append(
                f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="3" '
                f'fill="{color}"><title>{escape(title)}</title></rect>'
            )
    labels = render_month_labels(start, end)
    return "\n  ".join(cells + [labels])


def render_insight_row(label: str, value: str, label_x: int, value_x: int, y: int) -> str:
    return f"""
  <g>
    <text x="{label_x}" y="{y}" fill="{MUTED}" font-family="{FONT}" font-size="15">{escape(label)}</text>
    <text x="{value_x}" y="{y}" fill="{TEXT}" font-family="{FONT}" font-size="15" text-anchor="end">{escape(value)}</text>
  </g>"""


def render_svg(provider: dict[str, Any]) -> str:
    daily = daily_token_map(provider)
    end = max(daily) if daily else datetime.now(timezone.utc).date()
    start, display_end = display_range(end)

    lifetime_tokens = int(provider.get("totals", {}).get("totalTokens") or 0)
    last_30_tokens = int(provider.get("last30DaysTokens") or 0)
    peak_tokens = max(daily.values()) if daily else 0
    active_days = sum(1 for value in daily.values() if value > 0)
    current = current_streak(daily, end)
    longest = longest_streak(daily)
    updated = parse_updated_at(provider.get("updatedAt"), end)

    metric_top = 72
    metric_width = (WIDTH - (MARGIN * 2)) / 4
    metrics = [
        ("Lifetime tokens", short_number(lifetime_tokens)),
        ("Peak day", short_number(peak_tokens)),
        ("Current streak", f"{current} days"),
        ("Longest streak", f"{longest} days"),
    ]
    metric_groups = []
    separators = []
    for index, (label, value) in enumerate(metrics):
        x = MARGIN + index * metric_width
        metric_groups.append(render_metric(x, metric_top, metric_width, value, label))
        if index:
            line_x = MARGIN + index * metric_width
            separators.append(
                f'<line x1="{line_x:.2f}" y1="{metric_top + 12}" x2="{line_x:.2f}" '
                f'y2="{metric_top + 60}" stroke="{PANEL_STROKE}" stroke-width="1"/>'
            )

    subtitle = (
        f"{short_number(last_30_tokens)} tokens in the last 30 days - "
        f"{active_days} active days in available history - updated {updated}"
    )
    description = f"Codex activity heatmap. {subtitle}. Private fields omitted."

    heatmap = render_heatmap(daily, start, display_end, end)
    insight_y = 396
    insight_rows = [
        render_insight_row("Last 30 days", short_number(last_30_tokens), MARGIN, 388, insight_y),
        render_insight_row("Active days", str(active_days), MARGIN, 388, insight_y + 30),
        render_insight_row("Available since", min(daily).strftime("%b %-d, %Y") if daily else "n/a", MARGIN, 388, insight_y + 60),
        render_insight_row("Updated", updated, MARGIN, 388, insight_y + 90),
    ]

    legend_x = WIDTH - MARGIN - 190
    legend_cells = []
    for index, color in enumerate([EMPTY, *GRID_COLORS]):
        x = legend_x + index * 18
        legend_cells.append(
            f'<rect x="{x}" y="196" width="11" height="11" rx="3" fill="{color}"/>'
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">Codex usage activity graph</title>
  <desc id="desc">{escape(description)}</desc>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="18" fill="{BG}"/>
  <text x="{MARGIN}" y="36" fill="{TEXT}" font-family="{FONT}" font-size="22" font-weight="600">Codex Activity</text>
  <text x="{MARGIN}" y="59" fill="{MUTED}" font-family="{FONT}" font-size="13">{escape(subtitle)}</text>
  <rect x="{MARGIN}" y="{metric_top}" width="{WIDTH - (MARGIN * 2)}" height="82" rx="14" fill="{PANEL}" stroke="{PANEL_STROKE}"/>
  {"".join(separators)}
  {"".join(metric_groups)}
  <text x="{MARGIN}" y="196" fill="{TEXT}" font-family="{FONT}" font-size="18" font-weight="600">Token activity</text>
  <text x="{legend_x - 34}" y="198" fill="{MUTED}" font-family="{FONT}" font-size="12">Less</text>
  {"".join(legend_cells)}
  <text x="{legend_x + 100}" y="198" fill="{MUTED}" font-family="{FONT}" font-size="12">More</text>
  {heatmap}
  <text x="{MARGIN}" y="365" fill="{TEXT}" font-family="{FONT}" font-size="18" font-weight="600">Activity insights</text>
  {"".join(insight_rows)}
</svg>
"""


def main() -> None:
    provider = run_codexbar()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_svg(provider), encoding="utf-8")


if __name__ == "__main__":
    main()
