#!/usr/bin/env python3
"""
Generates stats.svg, streak.svg, langs.svg, year.svg from the GitHub
GraphQL API, using only the Python standard library so nothing can
break in CI.

Two determinism traps this avoids (see README Part 2):
  1. The contribution window is pinned to whole UTC days, not "the
     last 365 days from right now" — otherwise two runs minutes apart
     bucket days into different weeks and the sparkline shifts.
  2. Repositories are filtered to privacy: PUBLIC, so the workflow's
     GITHUB_TOKEN and a personal token report identical numbers.
"""
import json
import os
import urllib.request
from datetime import datetime, timedelta, timezone

GH_LOGIN = os.environ.get("GH_LOGIN")
TOKEN = os.environ.get("GITHUB_TOKEN")
API = "https://api.github.com/graphql"

RAMP = " .`:-=+*cs#%@"
FG_LIGHT = "#6e7681"
FG_DARK = "#c9d1d9"
ACCENT_LIGHT = "#0969da"
ACCENT_DARK = "#58a6ff"
FONT_STACK = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"

STYLE = (
    f"<style>.a{{fill:{FG_LIGHT}}}.b{{fill:{ACCENT_LIGHT}}}"
    f"@media(prefers-color-scheme:dark){{.a{{fill:{FG_DARK}}}.b{{fill:{ACCENT_DARK}}}}}</style>"
)


def gh_graphql(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(
        API,
        data=body,
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": GH_LOGIN or "stats-bot",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if "errors" in payload:
        raise RuntimeError(payload["errors"])
    return payload["data"]


def utc_window():
    """Whole-UTC-day window, pinned so re-runs are deterministic."""
    today = datetime.now(timezone.utc).replace(
        hour=23, minute=59, second=59, microsecond=0
    )
    start = (today - timedelta(days=364)).replace(hour=0, minute=0, second=0)
    return start.isoformat(), today.isoformat()


QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks {
          contributionDays { date contributionCount weekday }
        }
      }
    }
    repositories(first: 100, privacy: PUBLIC, ownerAffiliations: OWNER,
                  isFork: false) {
      nodes {
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def fetch():
    frm, to = utc_window()
    data = gh_graphql(QUERY, {"login": GH_LOGIN, "from": frm, "to": to})
    return data["user"]


def flatten_days(calendar):
    days = []
    for week in calendar["weeks"]:
        for d in week["contributionDays"]:
            days.append((d["date"], d["contributionCount"]))
    days.sort()
    return days


def compute_streaks(days):
    best_len, best_range = 0, ("", "")
    cur_len, cur_start = 0, None
    for date, count in days:
        if count > 0:
            cur_len += 1
            if cur_start is None:
                cur_start = date
            if cur_len > best_len:
                best_len = cur_len
                best_range = (cur_start, date)
        else:
            cur_len, cur_start = 0, None
    # current streak = trailing run ending today (or yesterday, to allow
    # for a day still in progress)
    current_len, current_range = 0, ("", "")
    run = 0
    start = None
    for date, count in days:
        if count > 0:
            run += 1
            if start is None:
                start = date
        else:
            run, start = 0, None
    if run:
        current_len, current_range = run, (start, days[-1][0])
    return (best_len, best_range), (current_len, current_range)


def weekly_totals(days):
    totals = []
    for i in range(0, len(days), 7):
        chunk = days[i : i + 7]
        totals.append(sum(c for _, c in chunk))
    return totals


def _embedded_font_face(role):
    """Inline @font-face from fonts/<role>.b64 if it exists (see
    scripts/subset_font.sh). An external font URL can't work here — these
    SVGs load through an <img> tag and browsers refuse subresource fetches
    for image documents, so the woff2 must be a base64 data URI baked into
    every file that uses it."""
    b64_path = os.path.join(os.path.dirname(__file__), "..", "fonts", f"{role}.b64")
    if not os.path.exists(b64_path):
        return ""
    with open(b64_path) as f:
        data = f.read().strip()
    return (
        f'@font-face{{font-family:"JBMono";src:url(data:font/woff2;base64,{data}) '
        f'format("woff2")}}'
    )


def svg_open(width, height, font_role="basic-latin"):
    font_face = _embedded_font_face(font_role)
    family = f'"JBMono",{FONT_STACK}' if font_face else FONT_STACK
    style = STYLE[:-8] + font_face + STYLE[-8:]  # insert before closing </style>
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{family}">{style}'
    )


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_stats_svg(total, weekly, path):
    """Compact card: just the headline number, sized to sit next to
    year.svg in a two-up row. `weekly` is accepted but unused here — kept
    in the signature in case a sparkline variant is wanted again later."""
    w, h, pad = 200, 110, 16
    p = [svg_open(w, h)]
    p.append(
        f'<text x="{pad}" y="{h/2 - 4:.0f}" class="b" font-size="34">{total:,}</text>'
        f'<text x="{pad}" y="{h/2 + 20:.0f}" class="a" font-size="11">contributions</text>'
        f'<text x="{pad}" y="{h/2 + 34:.0f}" class="a" font-size="11">in the last year</text>'
    )
    p.append("</svg>")
    with open(path, "w") as f:
        f.write("".join(p))


def build_streak_svg(best, current, path):
    """Compact card sized to sit next to langs.svg in a two-up row."""
    w, h, pad = 200, 110, 16
    p = [svg_open(w, h)]
    (best_len, (bs, be)) = best
    (cur_len, (cs, ce)) = current
    p.append(
        f'<text x="{pad}" y="30" class="b" font-size="20">{cur_len} day{"s" if cur_len != 1 else ""}</text>'
        f'<text x="{pad}" y="46" class="a" font-size="10">current streak</text>'
    )
    p.append(
        f'<text x="{pad}" y="78" class="a" font-size="16">{best_len} day{"s" if best_len != 1 else ""}</text>'
        f'<text x="{pad}" y="94" class="a" font-size="10">longest streak</text>'
    )
    p.append("</svg>")
    with open(path, "w") as f:
        f.write("".join(p))


def aggregate_languages(repo_nodes):
    totals = {}
    for repo in repo_nodes:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            totals[name] = totals.get(name, 0) + edge["size"]
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:6]
    grand = sum(v for _, v in ranked) or 1
    return [(name, size, size / grand) for name, size in ranked]


def build_langs_svg(ranked, path):
    """Sized to sit next to the compact streak.svg card in a two-up row."""
    w, pad = 260, 14
    row_h = 22
    h = pad * 2 + row_h * max(len(ranked), 1)
    p = [svg_open(w, h)]
    bar_x = pad + 110
    bar_w = w - bar_x - pad - 40
    for i, (name, size, frac) in enumerate(ranked):
        y = pad + i * row_h
        p.append(f'<text x="{pad}" y="{y + 14}" class="a" font-size="11">{esc(name)}</text>')
        p.append(f'<rect x="{bar_x}" y="{y + 3}" width="{bar_w}" height="10" class="a" opacity="0.15"/>')
        p.append(f'<rect x="{bar_x}" y="{y + 3}" width="{bar_w * frac:.1f}" height="10" class="b"/>')
        p.append(f'<text x="{bar_x + bar_w + 6}" y="{y + 12}" class="a" font-size="10">{frac * 100:.0f}%</text>')
    p.append("</svg>")
    with open(path, "w") as f:
        f.write("".join(p))


def build_year_svg(days, path):
    cols_per_row = 53  # ISO-week-ish grid, one column per week, one char per day below
    cell = 8
    w = pad = 14
    weeks = [days[i : i + 7] for i in range(0, len(days), 7)]
    width = pad * 2 + len(weeks) * cell
    height = pad * 2 + 7 * cell
    counts = [c for _, c in days]
    peak = max(counts) if counts else 1
    p = [svg_open(width, height)]
    n = len(RAMP)
    for wi, week in enumerate(weeks):
        for di, (date, count) in enumerate(week):
            level = 0 if peak == 0 else min(n - 1, int((count / peak) * (n - 1)))
            x = pad + wi * cell
            y = pad + di * cell
            opacity = 0.12 + (level / (n - 1)) * 0.88 if count else 0.12
            p.append(
                f'<rect x="{x}" y="{y}" width="{cell - 1.5}" height="{cell - 1.5}" '
                f'rx="1.5" class="a" opacity="{opacity:.2f}"><title>{date}: {count}</title></rect>'
            )
    p.append("</svg>")
    with open(path, "w") as f:
        f.write("".join(p))


def write_if_changed(path, builder, *args):
    tmp = path + ".tmp"
    builder(*args, tmp)
    if os.path.exists(path) and open(path).read() == open(tmp).read():
        os.remove(tmp)
        return
    os.replace(tmp, path)


def main():
    if not GH_LOGIN or not TOKEN:
        raise SystemExit("GH_LOGIN and GITHUB_TOKEN must be set")

    user = fetch()
    calendar = user["contributionsCollection"]["contributionCalendar"]
    total = calendar["totalContributions"]
    days = flatten_days(calendar)
    weekly = weekly_totals(days)
    best, current = compute_streaks(days)
    ranked_langs = aggregate_languages(user["repositories"]["nodes"])

    write_if_changed("stats.svg", build_stats_svg, total, weekly)
    write_if_changed("streak.svg", build_streak_svg, best, current)
    write_if_changed("langs.svg", build_langs_svg, ranked_langs)
    write_if_changed("year.svg", build_year_svg, days)


if __name__ == "__main__":
    main()
