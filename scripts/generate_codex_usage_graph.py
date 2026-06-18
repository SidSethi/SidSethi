#!/usr/bin/env python3
"""Generate a GitHub-profile-safe Codex usage graph from CodexBar data."""

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
DAYS = 30

WIDTH = 760
HEIGHT = 190
PADDING_X = 28
TITLE_Y = 32
SUBTITLE_Y = 54
PLOT_TOP = 78
PLOT_HEIGHT = 78
PLOT_BOTTOM = PLOT_TOP + PLOT_HEIGHT
BAR_GAP = 6
BAR_RADIUS = 4

BG = "#ffffff"
TEXT = "#24292f"
MUTED = "#57606a"
AXIS = "#d0d7de"
EMPTY = "#ebedf0"
COLORS = ["#9be9a8", "#40c463", "#30a14e", "#216e39"]


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


def short_number(value: int) -> str:
    units = [
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ]
    for size, suffix in units:
        if value >= size:
            number = value / size
            return f"{number:.2f}{suffix}" if number < 10 else f"{number:.1f}{suffix}"
    return str(value)


def bar_color(tokens: int, max_tokens: int) -> str:
    if tokens <= 0 or max_tokens <= 0:
        return EMPTY
    ratio = math.log10(tokens + 1) / math.log10(max_tokens + 1)
    if ratio < 0.35:
        return COLORS[0]
    if ratio < 0.58:
        return COLORS[1]
    if ratio < 0.8:
        return COLORS[2]
    return COLORS[3]


def bar_height(tokens: int, max_tokens: int) -> int:
    if tokens <= 0 or max_tokens <= 0:
        return 4
    ratio = math.log10(tokens + 1) / math.log10(max_tokens + 1)
    return max(6, round(ratio * PLOT_HEIGHT))


def render_svg(provider: dict[str, Any]) -> str:
    daily = {
        parse_date(item["date"]): int(item.get("totalTokens", 0))
        for item in provider.get("daily", [])
        if item.get("date")
    }
    end = max(daily) if daily else datetime.now(timezone.utc).date()
    start = end - timedelta(days=DAYS - 1)
    dates = [start + timedelta(days=index) for index in range(DAYS)]
    values = [daily.get(day, 0) for day in dates]

    total = sum(values)
    active_days = sum(1 for value in values if value > 0)
    max_tokens = max(values) if values else 0
    updated = parse_updated_at(provider.get("updatedAt"), end)

    plot_width = WIDTH - (PADDING_X * 2)
    bar_width = (plot_width - (BAR_GAP * (DAYS - 1))) / DAYS

    subtitle = (
        f"Last {DAYS} days: {short_number(total)} tokens "
        f"across {active_days} active days - updated {updated}"
    )

    bars: list[str] = []
    for index, (day, tokens) in enumerate(zip(dates, values, strict=True)):
        height = bar_height(tokens, max_tokens)
        x = PADDING_X + index * (bar_width + BAR_GAP)
        y = PLOT_BOTTOM - height
        color = bar_color(tokens, max_tokens)
        title = f"{day.isoformat()}: relative Codex activity"
        bars.append(
            f'<rect x="{x:.2f}" y="{y}" width="{bar_width:.2f}" height="{height}" '
            f'rx="{BAR_RADIUS}" fill="{color}"><title>{escape(title)}</title></rect>'
        )

    start_label = start.strftime("%b %-d")
    end_label = end.strftime("%b %-d")

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">
  <title id="title">Codex usage activity graph</title>
  <desc id="desc">{escape(subtitle)}</desc>
  <rect width="{WIDTH}" height="{HEIGHT}" rx="8" fill="{BG}"/>
  <text x="{PADDING_X}" y="{TITLE_Y}" fill="{TEXT}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="18" font-weight="600">Codex usage</text>
  <text x="{PADDING_X}" y="{SUBTITLE_Y}" fill="{MUTED}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="13">{escape(subtitle)}</text>
  <line x1="{PADDING_X}" y1="{PLOT_BOTTOM}" x2="{WIDTH - PADDING_X}" y2="{PLOT_BOTTOM}" stroke="{AXIS}" stroke-width="1"/>
  {"".join(bars)}
  <text x="{PADDING_X}" y="{PLOT_BOTTOM + 24}" fill="{MUTED}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12">{escape(start_label)}</text>
  <text x="{WIDTH - PADDING_X}" y="{PLOT_BOTTOM + 24}" fill="{MUTED}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif" font-size="12" text-anchor="end">{escape(end_label)}</text>
</svg>
"""


def main() -> None:
    provider = run_codexbar()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(render_svg(provider), encoding="utf-8")


if __name__ == "__main__":
    main()
