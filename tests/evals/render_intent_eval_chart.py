from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


_BAR_COLORS = ["#1d4ed8", "#15803d", "#d97706", "#b91c1c", "#6d28d9", "#0f766e"]


def _load_results(results_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(results_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_path"] = path
        records.append(payload)
    if not records:
        raise SystemExit(f"No JSON result files found in {results_dir}")
    return records


def _build_svg(records: list[dict[str, Any]], *, title: str, subtitle: str) -> str:
    ranked_records = sorted(
        records,
        key=lambda item: (item["pass_rate"], item["passed"], item["model"]),
        reverse=True,
    )

    width = 960
    header_height = 110
    row_height = 78
    footer_height = 60
    height = header_height + row_height * len(ranked_records) + footer_height

    left_margin = 240
    right_margin = 90
    chart_width = width - left_margin - right_margin
    bar_height = 28
    bar_radius = 8

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title subtitle">',
        "  <defs>",
        '    <linearGradient id="bg" x1="0" x2="1" y1="0" y2="1">',
        '      <stop offset="0%" stop-color="#fcfbf7" />',
        '      <stop offset="100%" stop-color="#eef4ff" />',
        "    </linearGradient>",
        "  </defs>",
        '  <rect width="100%" height="100%" fill="url(#bg)" rx="18" ry="18" />',
        f'  <title id="title">{escape(title)}</title>',
        f'  <desc id="subtitle">{escape(subtitle)}</desc>',
        f'  <text x="36" y="44" font-family="Segoe UI, Arial, sans-serif" font-size="28" font-weight="700" fill="#111827">{escape(title)}</text>',
        f'  <text x="36" y="72" font-family="Segoe UI, Arial, sans-serif" font-size="14" fill="#475569">{escape(subtitle)}</text>',
    ]

    grid_y = header_height - 12
    for step in range(0, 101, 25):
        x = left_margin + (chart_width * step / 100)
        lines.append(
            f'  <line x1="{x:.1f}" y1="{grid_y}" x2="{x:.1f}" y2="{height - footer_height + 6}" stroke="#cbd5e1" stroke-dasharray="4 8" />'
        )
        lines.append(
            f'  <text x="{x:.1f}" y="{grid_y - 14}" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#64748b">{step}%</text>'
        )

    for index, record in enumerate(ranked_records):
        top = header_height + index * row_height
        bar_y = top + 24
        bar_width = chart_width * float(record["pass_rate"])
        color = _BAR_COLORS[index % len(_BAR_COLORS)]
        label = f'{record["model"]} ({record["reasoning_effort"]})'
        score = f'{record["passed"]}/{record["total"]}'
        percent = f'{round(float(record["pass_rate"]) * 100):d}%'

        lines.extend(
            [
                f'  <text x="36" y="{top + 28}" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="600" fill="#0f172a">{escape(label)}</text>',
                f'  <text x="36" y="{top + 50}" font-family="Segoe UI, Arial, sans-serif" font-size="13" fill="#475569">{escape(score)} cases passed</text>',
                f'  <rect x="{left_margin}" y="{bar_y}" width="{chart_width}" height="{bar_height}" rx="{bar_radius}" ry="{bar_radius}" fill="#e2e8f0" />',
                f'  <rect x="{left_margin}" y="{bar_y}" width="{bar_width:.1f}" height="{bar_height}" rx="{bar_radius}" ry="{bar_radius}" fill="{color}" />',
                f'  <text x="{left_margin + chart_width + 14}" y="{bar_y + 20}" font-family="Segoe UI, Arial, sans-serif" font-size="16" font-weight="700" fill="#111827">{percent}</text>',
            ]
        )

    lines.append(
        f'  <text x="36" y="{height - 22}" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#64748b">Source: tests/evals/results/*.json</text>'
    )
    lines.append("</svg>")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Render an SVG chart from intent eval JSON results.")
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("tests/evals/results"),
        help="Directory containing JSON result files from live intent eval runs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("docs/assets/intent-eval-model-comparison.svg"),
        help="Path to write the SVG chart.",
    )
    parser.add_argument(
        "--title",
        default="Intent Parser Eval Pass Rate",
        help="Chart title.",
    )
    parser.add_argument(
        "--subtitle",
        default="Live OpenAIIntentParser.parse() sample run on 11 fixture cases",
        help="Chart subtitle.",
    )
    args = parser.parse_args()

    records = _load_results(args.results_dir)
    svg = _build_svg(records, title=args.title, subtitle=args.subtitle)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(svg, encoding="utf-8")
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
