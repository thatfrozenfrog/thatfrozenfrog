#!/usr/bin/env python3
"""Draw the profile README's stat graphics from the GitHub GraphQL API.

No third-party services and no dependencies — standard library only.

Outputs, all sharing one visual language with ascii.svg (the portrait):
  stats.svg   hero total + weekly sparkline
  streak.svg  current and longest streak
  langs.svg   top languages, by bytes and by repo count
  year.svg    the year as a character map, in the portrait's own ramp

Every file uses the portrait's grey ink, a monospace face, a transparent
background, and the same left-to-right clipPath reveal with a cursor riding
the edge. Motion is SMIL because GitHub strips <script> from READMEs.

Env:
  GITHUB_TOKEN  optional if `gh auth token` is configured
  GH_LOGIN      user to summarise (default: thatfrozenfrog)
  OUT_DIR       where to write (default: repository root)
"""
import argparse
import base64
import functools
import json
import os
import re
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone

API = "https://api.github.com/graphql"

# Two things are pinned for determinism, both learned the hard way:
#  * the contribution window, to whole UTC days — otherwise "the past year" is
#    measured from request time and days drift between week buckets, moving the
#    sparkline a fraction of a pixel and committing noise every night;
#  * privacy: PUBLIC on repositories — otherwise a personal token sees private
#    repos and a workflow token doesn't, so language totals disagree.
QUERY = """
query($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { contributionCount date weekday } }
      }
    }
    repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                 privacy: PUBLIC) {
      nodes {
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

# GitHub native palette:
# Contribution green for data curves, bars, and active calendar blocks;
# GitHub primary ink for emphasis; GitHub border rule & surface.
LIGHT = dict(data="#1f883d", emph="#1f2328", dim="#656d76",
             rule="#d0d7de", surface="#ffffff")
DARK = dict(data="#3fb950", emph="#f0f6fc", dim="#8b949e",
            rule="#30363d", surface="#0d1117")
# JBMono is the inlined subset below; the rest is a fallback for the unlikely
# case a renderer ignores the embedded face.
MONO = ("JBMono,ui-monospace,SFMono-Regular,Menlo,Consolas,"
        "&apos;Liberation Mono&apos;,monospace")
FONT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")


@functools.lru_cache(maxsize=None)
def face(filename, weight):
    """One @font-face rule with the subset inlined as a data URI.

    An external font URL cannot work here: these SVGs are loaded through <img>,
    and browsers refuse to fetch subresources for an image document. Inlining is
    also what pins the advance width — the portrait's grid assumes 0.600 em, and
    a viewer whose default monospace is narrower would otherwise see it squeezed.
    """
    with open(os.path.join(FONT_DIR, filename), "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    return (f"@font-face{{font-family:JBMono;font-style:normal;"
            f"font-weight:{weight};font-display:block;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")


def font_text():
    """Basic latin, both weights — for the data graphics."""
    return face("jbmono-400.woff2", 400) + face("jbmono-600.woff2", 600)


def font_head():
    """Basic latin semibold for section headings."""
    return face("jbmono-600.woff2", 600)

WIDTH = 620            # every graphic shares one column width
LEFT = 34              # shared left inset, so stacked blocks line up
                       # (year.svg needs it for the weekday gutter)
REVEAL = 1.30          # seconds; matches the portrait's cadence
RAMP = [" ", ":", "+", "#", "@"]      # steps of the portrait's own ramp
MON = ["jan", "feb", "mar", "apr", "may", "jun",
       "jul", "aug", "sep", "oct", "nov", "dec"]
MON_FULL = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pretty_date_year(iso):
    if not iso:
        return "Mar 7, 2022"
    d = date.fromisoformat(iso[:10])
    return f"{MON_FULL[d.month - 1]} {d.day}, {d.year}"


def pretty_date_span(start_iso, end_iso):
    if not start_iso or not end_iso:
        return "&#8212;"
    d1 = date.fromisoformat(start_iso[:10])
    d2 = date.fromisoformat(end_iso[:10])
    if d1 == d2:
        return f"{MON_FULL[d1.month - 1]} {d1.day}, {d1.year}"
    return f"{MON_FULL[d1.month - 1]} {d1.day}, {d1.year} &#8211; {MON_FULL[d2.month - 1]} {d2.day}, {d2.year}"


# ---------------------------------------------------------------- data

def window():
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    return (f"{start.isoformat()}T00:00:00Z", f"{today.isoformat()}T23:59:59Z")


def fetch(login, token):
    headers = {"Authorization": f"bearer {token}",
               "Content-Type": "application/json",
               "User-Agent": f"{login}-profile-stats"}

    # 1. Fetch user metadata (account creation and contribution years)
    meta_query = """
    query($login: String!) {
      user(login: $login) {
        createdAt
        contributionsCollection {
          contributionYears
        }
      }
    }
    """
    req1 = urllib.request.Request(
        API, data=json.dumps({"query": meta_query, "variables": {"login": login}}).encode(),
        headers=headers)
    with urllib.request.urlopen(req1, timeout=30) as r:
        meta_payload = json.load(r)
    if "errors" in meta_payload:
        raise SystemExit(f"GraphQL errors: {meta_payload['errors']}")
    user_meta = (meta_payload.get("data") or {}).get("user")
    if not user_meta:
        raise SystemExit(f"no such user: {login}")

    created_at = user_meta.get("createdAt")
    years = user_meta.get("contributionsCollection", {}).get("contributionYears", [])

    # 2. Build multi-year query
    year_fields = []
    for y in years:
        year_fields.append(f"""
        y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{y}-12-31T23:59:59Z") {{
          contributionCalendar {{
            totalContributions
            weeks {{ contributionDays {{ contributionCount date }} }}
          }}
        }}""")

    since, until = window()
    main_query = f"""
    query($login: String!, $from: DateTime!, $to: DateTime!) {{
      user(login: $login) {{
        contributionsCollection(from: $from, to: $to) {{
          contributionCalendar {{
            totalContributions
            weeks {{ contributionDays {{ contributionCount date weekday }} }}
          }}
        }}
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {{
          nodes {{
            languages(first: 12, orderBy: {{field: SIZE, direction: DESC}}) {{
              edges {{ size node {{ name }} }}
            }}
          }}
        }}
        {"".join(year_fields)}
      }}
    }}
    """
    body = json.dumps({"query": main_query, "variables": {"login": login, "from": since, "to": until}}).encode()
    req2 = urllib.request.Request(API, data=body, headers=headers)
    with urllib.request.urlopen(req2, timeout=30) as r:
        payload = json.load(r)
    if "errors" in payload:
        raise SystemExit(f"GraphQL errors: {payload['errors']}")
    user = (payload.get("data") or {}).get("user")
    if not user:
        raise SystemExit(f"no such user: {login}")
    user["createdAt"] = created_at
    user["contributionYears"] = years
    return user


def pretty(iso):
    d = date.fromisoformat(iso)
    return f"{MON[d.month - 1]} {d.day}"


def streaks(days):
    """Current and longest runs of days with at least one contribution.

    A zero on the final day doesn't break the current streak — the day isn't
    over yet. Any earlier zero does.
    """
    best = dict(length=0, start=None, end=None)
    run, run_start = 0, None
    for d in days:
        if d["contributionCount"] > 0:
            run += 1
            run_start = run_start or d["date"]
            if run > best["length"]:
                best = dict(length=run, start=run_start, end=d["date"])
        else:
            run, run_start = 0, None

    cur = dict(length=0, start=None, end=None)
    tail = days[:-1] if days and days[-1]["contributionCount"] == 0 else days
    for d in reversed(tail):
        if d["contributionCount"] == 0:
            break
        cur["length"] += 1
        cur["start"] = d["date"]
        cur["end"] = cur["end"] or d["date"]
    return cur, best


def languages(repos):
    by_size, by_repo = {}, {}
    for node in repos:
        edges = (node.get("languages") or {}).get("edges") or []
        for e in edges:
            name = e["node"]["name"]
            by_size[name] = by_size.get(name, 0) + e["size"]
        if edges:                       # primary language of the repo
            top = edges[0]["node"]["name"]
            by_repo[top] = by_repo.get(top, 0) + 1

    def rank(d):
        # sort by value, then name, so equal values never reorder between runs
        return sorted(d.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

    return rank(by_size), rank(by_repo)


def summarise(user):
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = [w["contributionDays"] for w in cal["weeks"]]
    days = [d for w in weeks for d in w]
    weekly = [sum(d["contributionCount"] for d in w) for w in weeks]
    by_size, by_repo = languages(user["repositories"]["nodes"])

    # Multi-year calculations
    years = user.get("contributionYears") or []
    all_days = []
    lifetime_total = 0
    for y in sorted(years):
        y_cal = (user.get(f"y{y}") or {}).get("contributionCalendar")
        if y_cal:
            lifetime_total += y_cal.get("totalContributions", 0)
            for w in y_cal.get("weeks", []):
                all_days.extend(w.get("contributionDays", []))

    if all_days:
        days_by_date = {d["date"]: d["contributionCount"] for d in all_days}
        sorted_dates = sorted(days_by_date.keys())

        # Longest streak across all recorded history
        best = dict(length=0, start=None, end=None)
        run, run_start = 0, None
        for dt in sorted_dates:
            if days_by_date[dt] > 0:
                run += 1
                run_start = run_start or dt
                if run > best["length"]:
                    best = dict(length=run, start=run_start, end=dt)
            else:
                run, run_start = 0, None

        # Current streak
        cur = dict(length=0, start=None, end=None)
        tail = sorted_dates[:-1] if sorted_dates and days_by_date[sorted_dates[-1]] == 0 else sorted_dates
        for dt in reversed(tail):
            if days_by_date[dt] == 0:
                break
            cur["length"] += 1
            cur["start"] = dt
            cur["end"] = cur["end"] or dt
    else:
        cur, best = streaks(days)
        lifetime_total = cal["totalContributions"]

    created_raw = user.get("createdAt")
    if created_raw:
        dt = datetime.fromisoformat(created_raw.replace("Z", "+00:00")).astimezone(timezone(timedelta(hours=-5)))
        created_pretty = f"{MON_FULL[dt.month - 1]} {dt.day}, {dt.year}"
    else:
        created_pretty = "Mar 7, 2022"

    today_date = datetime.now(timezone.utc).date()
    today_pretty = f"{MON_FULL[today_date.month - 1]} {today_date.day}"

    return dict(
        total=cal["totalContributions"],
        lifetime_total=lifetime_total,
        active=sum(1 for d in days if d["contributionCount"] > 0),
        best_week=max(weekly) if weekly else 0,
        weekly=weekly, weeks=weeks,
        current=cur, longest=best,
        by_size=by_size, by_repo=by_repo,
        created_pretty=created_pretty,
        today_pretty=today_pretty)


# ---------------------------------------------------------------- drawing

def style(extra="", font=None):
    def block(t):
        return (f".d-f{{fill:{t['data']}}}.d-s{{stroke:{t['data']}}}"
                f".e-f{{fill:{t['emph']}}}.m-f{{fill:{t['dim']}}}"
                f".u-s{{stroke:{t['rule']}}}.r{{stroke:{t['surface']}}}")
    return (f"<style>{font or font_text()}"
            f"{block(LIGHT)}.w{{fill:{LIGHT['data']};opacity:.13}}{extra}"
            f"@media(prefers-color-scheme:dark){{{block(DARK)}"
            f".w{{fill:{DARK['data']};opacity:.16}}}}</style>")


def head(w, h, font=None, extra=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
            f'viewBox="0 0 {w} {h}" fill="none" font-family="{MONO}">'
            + style(extra=extra, font=font))


def fade(delay, dur=0.45):
    return (f'<animate attributeName="opacity" from="0" to="1" '
            f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/>')


def wipe(cid, x, y, w, h, delay, dur=REVEAL):
    """clipPath reveal plus the cursor block that rides its edge."""
    clip = (f'<clipPath id="{cid}"><rect x="{x}" y="{y}" height="{h}" width="0">'
            f'<animate attributeName="width" from="0" to="{w}" '
            f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/></rect></clipPath>')
    cursor = (f'<rect y="{y}" width="2" height="{h}" class="d-f" opacity="0">'
              f'<animate attributeName="x" from="{x}" to="{x + w}" '
              f'begin="{delay:.2f}s" dur="{dur}s" fill="freeze"/>'
              f'<set attributeName="opacity" to="0.55" begin="{delay:.2f}s"/>'
              f'<set attributeName="opacity" to="0" '
              f'begin="{delay + dur:.2f}s"/></rect>')
    return clip, cursor


def label(x, y, text, size=11, cls="m-f", anchor="start", extra=""):
    a = f' text-anchor="{anchor}"' if anchor != "start" else ""
    return (f'<text x="{x}" y="{y}" class="{cls}" font-size="{size}"{a}'
            f'{extra}>{text}</text>')


def hbar(x, y, w, h, cls="d-f", r=3.0):
    """Horizontal bar: rounded data-end on the right, square at the baseline."""
    if w <= 0.6:
        return ""
    r = min(r, h / 2.0, w)
    return (f'<path d="M{x:.1f} {y:.1f}H{x + w - r:.1f}'
            f'Q{x + w:.1f} {y:.1f} {x + w:.1f} {y + r:.1f}'
            f'V{y + h - r:.1f}Q{x + w:.1f} {y + h:.1f} {x + w - r:.1f} {y + h:.1f}'
            f'H{x:.1f}Z" class="{cls}"/>')


def draw_stats(s):
    """Hero number, the two secondary counts, and the weekly sparkline."""
    H = 148
    weekly = s["weekly"] or [0]
    peak = max(weekly) or 1
    p = [head(WIDTH, H)]
    p.append(f'<g opacity="0">{fade(0.10)}'
             + label(0, 50, s["total"], 52, "e-f", extra=' font-weight="600"')
             + label(0, 72, "contributions in the last year", 12) + '</g>')
    for i, (val, lab) in enumerate([(s["active"], "active days"),
                                    (s["best_week"], "best week")]):
        p.append(f'<g opacity="0">{fade(0.30 + i * 0.12)}'
                 + label(WIDTH, 30 + i * 40, val, 19, "e-f", "end",
                         ' font-weight="600"')
                 + label(WIDTH, 47 + i * 40, lab, 11, "m-f", "end") + '</g>')

    base, top = H - 10, H - 58
    span = base - top
    step = WIDTH / max(len(weekly) - 1, 1)
    pts = [(i * step, base - (v / peak) * span) for i, v in enumerate(weekly)]
    clip, cursor = wipe("rs", 0, top - 6, WIDTH, span + 8, 0.50)
    p.append(clip)
    p.append('<g clip-path="url(#rs)">')
    p.append(f'<path d="M{pts[0][0]:.1f} {base:.1f}'
             + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts)
             + f'L{pts[-1][0]:.1f} {base:.1f}Z" class="w"/>')
    p.append(f'<path d="M{pts[0][0]:.1f} {pts[0][1]:.1f}'
             + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts[1:])
             + f'" class="d-s" stroke-width="2" stroke-linejoin="round" '
             f'stroke-linecap="round"/>')
    p.append("</g>")
    p.append(cursor)
    ex, ey = pts[-1]
    p.append(f'<circle cx="{ex - 2:.1f}" cy="{ey:.1f}" r="4.5" class="e-f r" '
             f'stroke-width="2" opacity="0">{fade(0.50 + REVEAL, 0.35)}</circle>')
    p.append("</svg>")
    return "".join(p)


def draw_streak(s):
    """3-column streak card matching GitHub streak stats in theme:
    Total Contributions | Current Streak (with flame & ring) | Longest Streak
    """
    H = 156
    p = [head(WIDTH, H)]

    # Outer card border with rounded corners
    p.append(f'<rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{H - 1}" rx="8" '
             f'class="u-s" stroke-width="1" opacity="0">{fade(0.10)}</rect>')

    # Vertical hairlines separating columns
    p.append(f'<line x1="206" y1="22" x2="206" y2="134" class="u-s" stroke-width="1" opacity="0">{fade(0.18)}</line>')
    p.append(f'<line x1="414" y1="22" x2="414" y2="134" class="u-s" stroke-width="1" opacity="0">{fade(0.18)}</line>')

    # Column 1 (Left): Total Contributions
    lt = s.get("lifetime_total", s["total"])
    lt_str = f"{lt:,}"
    cp = s.get("created_pretty", "Mar 7, 2022")
    created_span = f"{cp} &#8211; Present"
    p.append(f'<g opacity="0">{fade(0.14)}'
             + label(103, 62, lt_str, 30, "e-f", "middle", ' font-weight="600"')
             + label(103, 90, "Total Contributions", 12.5, "e-f", "middle", ' font-weight="600"')
             + label(103, 112, created_span, 10.5, "m-f", "middle")
             + '</g>')

    # Column 2 (Center): Current Streak with Flame & Ring
    cur = s["current"]
    cur_len = cur["length"]
    today_str = s.get("today_pretty", "Today")
    cur_span = pretty_date_span(cur["start"], cur["end"]) if cur_len else today_str

    flame_d = (
        "M 310 12 "
        "C 305 18 300 23.5 300 30 "
        "C 300 35.5 304.5 40 310 40 "
        "C 315.5 40 320 35.5 320 30 "
        "C 320 24.5 316 20.5 313.5 17 "
        "C 313.8 19.5 312 21.5 310 21.5 "
        "C 308 21.5 307 20 307.5 18 "
        "C 308.2 16 309.2 14 310 12 Z "
        "M 310 26 "
        "C 308.5 28 307.5 29.5 307.5 31 "
        "C 307.5 32.4 308.6 33.5 310 33.5 "
        "C 311.4 33.5 312.5 32.4 312.5 31 "
        "C 312.5 29.5 311.5 28 310 26 Z"
    )
    ring_d = "M 302.0 27.1 A 30 30 0 1 0 318.0 27.1"
    flame_cls = "d-f" if cur_len > 0 else "d-f"
    ring_cls = "d-s" if cur_len > 0 else "u-s"

    p.append(f'<g opacity="0">{fade(0.20)}'
             f'<path d="{flame_d}" fill-rule="evenodd" class="{flame_cls}"/>'
             f'<path d="{ring_d}" fill="none" class="{ring_cls}" stroke-width="3.5" stroke-linecap="round"/>'
             + label(310, 68, f"{cur_len}", 26, "e-f", "middle", ' font-weight="600"')
             + label(310, 114, "Current Streak", 13, "e-f", "middle", ' font-weight="600"')
             + label(310, 132, cur_span, 10.5, "m-f", "middle")
             + '</g>')

    # Column 3 (Right): Longest Streak
    longest = s["longest"]
    long_len = longest["length"]
    long_span = pretty_date_span(longest["start"], longest["end"]) if long_len else "&#8212;"
    p.append(f'<g opacity="0">{fade(0.26)}'
             + label(517, 62, f"{long_len}", 30, "e-f", "middle", ' font-weight="600"')
             + label(517, 90, "Longest Streak", 12.5, "e-f", "middle", ' font-weight="600"')
             + label(517, 112, long_span, 10.5, "m-f", "middle")
             + '</g>')

    p.append("</svg>")
    return "".join(p)


def draw_langs(s):
    """Two small charts: share of bytes, and count of repos by main language."""
    rows = max(len(s["by_size"]), len(s["by_repo"]), 1)
    H = 26 + rows * 22 + 6
    colw = (WIDTH - LEFT - 30) / 2
    name_w, bar_max = 82, colw - 82 - 44

    p = [head(WIDTH, H)]
    groups = [(LEFT, "by bytes", s["by_size"], True),
              (LEFT + colw + 30, "by repos", s["by_repo"], False)]
    for gi, (gx, title, data, as_pct) in enumerate(groups):
        p.append(f'<g opacity="0">{fade(0.10 + gi * 0.10)}'
                 + label(gx, 12, title.upper(), 9, "m-f",
                         extra=' letter-spacing="1.3"') + '</g>')
        if not data:
            continue
        top = max(v for _, v in data) or 1
        total = sum(v for _, v in data) or 1
        cid = f"rl{gi}"
        clip, cursor = wipe(cid, gx + name_w, 20, bar_max, rows * 22,
                            0.34 + gi * 0.12, 0.95)
        p.append(clip)
        for ri, (name, val) in enumerate(data):
            y = 26 + ri * 22
            shown = (f"{val / total * 100:.0f}%" if as_pct else f"{val}")
            p.append(f'<g opacity="0">{fade(0.24 + gi * 0.10 + ri * 0.05)}'
                     + label(gx, y + 8, name.lower()[:11], 11, "e-f")
                     + label(gx + colw - 6, y + 8, shown, 11, "m-f", "end")
                     + '</g>')
            p.append(f'<g clip-path="url(#{cid})">'
                     + hbar(gx + name_w, y, bar_max * val / top, 7)
                     + '</g>')
        p.append(cursor)
    p.append("</svg>")
    return "".join(p)


def draw_heading(word):
    """A section heading in the mono face, with a hairline running right.

    GitHub strips <style> and style= from markdown, so a real markdown heading
    can only ever be GitHub's own sans. Rendering the label as an SVG is the
    only way to put the page's own typeface on it. The rule starts past the
    longest plausible advance (0.6em is the widest common monospace ratio), so
    a narrower font on the viewer's machine widens the gap slightly rather than
    colliding with the text.
    """
    FS = 16
    H = 26
    text_end = len(word) * FS * 0.6 + 18
    p = [head(WIDTH, H, font=font_head())]
    p.append(label(0, 18, word, FS, "e-f", extra=' font-weight="600"'))
    p.append(f'<line x1="{text_end:.0f}" y1="12.5" x2="{WIDTH}" y2="12.5" '
             f'class="u-s" stroke-width="1"/>')
    p.append("</svg>")
    return "".join(p)


def draw_banned():
    """Big bold red text: (USER WAS BANNED FOR THIS POST)"""
    FS = 17
    H = 26
    text = "(USER WAS BANNED FOR THIS POST)"
    W = int(len(text) * FS * 0.60 + 16)
    banned_css = (
        ".b-f{fill:#AF0A0F;font-weight:700;letter-spacing:0.3px;}"
        "@media(prefers-color-scheme:dark){.b-f{fill:#f85149;}}"
    )
    p = [head(W, H, font=font_head(), extra=banned_css)]
    p.append(label(0, 19, text, FS, "b-f", extra=' font-weight="700"'))
    p.append("</svg>")
    return "".join(p)



def draw_year(s):
    """Seven rows by fifty-three weeks, intensity as a character."""
    FS, LH, COLW = 9.2, 11.0, 2
    CW = FS * 0.6
    pad_l, pad_t = LEFT, 44
    weeks = s["weeks"]
    ncols = len(weeks) * COLW
    H = int(pad_t + 7 * LH + 26)

    def level(v):
        for i, cut in enumerate((0, 2, 5, 9)):
            if v <= cut:
                return i
        return 4

    p = [head(WIDTH, H)]
    p.append(f'<g opacity="0">{fade(0.10)}'
             + label(pad_l, 16, "THE YEAR", 9, "m-f",
                     extra=' letter-spacing="1.3"')
             + label(pad_l, 32, f"{s['active']} of "
                     f"{sum(len(w) for w in weeks)} days had a contribution", 11)
             + '</g>')

    # ramp legend, so the encoding is never carried by shade alone
    lx = WIDTH - 6
    p.append(f'<g opacity="0">{fade(1.30)}'
             + label(lx - 78, 32, "less", 9, "m-f", "end")
             + f'<text xml:space="preserve" x="{lx - 72}" y="32" class="d-f" '
             f'font-size="{FS}">{" ".join(RAMP[1:])}</text>'
             + label(lx, 32, "more", 9, "m-f", "end") + '</g>')

    for r in range(7):
        chars = []
        for w in weeks:
            day = next((d for d in w if d.get("weekday") == r), None)
            v = day["contributionCount"] if day else 0
            chars.append(RAMP[level(v)] * COLW)
        line = "".join(chars).rstrip()
        if not line:
            continue
        y = pad_t + r * LH
        w_px = max(len(line), 1) * CW
        cid = f"ry{r}"
        delay = 0.30 + r * 0.07
        p.append(f'<clipPath id="{cid}"><rect x="{pad_l}" y="{y}" '
                 f'height="{LH}" width="0"><animate attributeName="width" '
                 f'from="0" to="{w_px:.1f}" begin="{delay:.2f}s" dur="0.40s" '
                 f'fill="freeze"/></rect></clipPath>')
        safe = line.replace("&", "&amp;").replace("<", "&lt;")
        p.append(f'<g clip-path="url(#{cid})"><text xml:space="preserve" '
                 f'x="{pad_l}" y="{y + FS - 0.6:.1f}" class="d-f" '
                 f'font-size="{FS}">{safe}</text></g>')

    for r, lab in ((1, "mon"), (3, "wed"), (5, "fri")):
        p.append(label(pad_l - 7, pad_t + r * LH + FS - 0.6, lab, 9, "m-f",
                       "end"))

    last_m, last_x = None, -999.0
    base_y = pad_t + 7 * LH + 13
    for i, w in enumerate(weeks):
        m = int(w[0]["date"][5:7])
        x = pad_l + i * COLW * CW
        if m != last_m and i < len(weeks) - 1 and x - last_x >= 34:
            p.append(label(x, base_y, MON[m - 1], 9, "m-f"))
            last_x = x
        last_m = m

    p.append("</svg>")
    return "".join(p)


# ---------------------------------------------------------------- main

def write(path, svg):
    old = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    if old == svg:
        return False
    with open(path, "w", encoding="utf-8") as f:
        f.write(svg)
    return True


def get_token(cli_token=None):
    if cli_token:
        return cli_token
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    try:
        res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, check=True)
        t = res.stdout.strip()
        if t:
            return t
    except Exception:
        pass
    return None


def mock_summary():
    import random
    weeks = []
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=364)
    cur_date = start
    for w in range(53):
        days = []
        for d in range(7):
            cnt = random.choices([0, 1, 3, 6, 12], weights=[45, 25, 18, 8, 4])[0]
            days.append({"contributionCount": cnt, "date": cur_date.isoformat(), "weekday": d})
            cur_date += timedelta(days=1)
        weeks.append(days)
    days = [d for w in weeks for d in w]
    weekly = [sum(d["contributionCount"] for d in w) for w in weeks]
    return dict(
        total=511,
        lifetime_total=1356,
        active=128,
        best_week=52,
        weekly=weekly, weeks=weeks,
        current=dict(length=0, start=None, end=None),
        longest=dict(length=17, start="2024-11-19", end="2024-12-05"),
        by_size=[("JavaScript", 1152312), ("TypeScript", 192881), ("Python", 56426), ("HTML", 49022), ("Rust", 48273)],
        by_repo=[("JavaScript", 8), ("TypeScript", 6), ("Python", 4), ("Nim", 3), ("C++", 2)],
        created_pretty="Mar 7, 2022",
        today_pretty=f"{MON_FULL[today.month - 1]} {today.day}"
    )


def update_readme_datetimes(readme_path, now=None):
    """Scan README.md for 4chan post timestamps and update to current runtime.

    Maintains realistic sequential post times:
      OP:      current runtime (T)
      Reply 1: T + 15s
      Reply 2: T + 37s
      Reply 3: T + 65s
    """
    if not os.path.exists(readme_path):
        return False

    if now is None:
        tz_name = os.environ.get("TZ")
        if tz_name:
            try:
                import zoneinfo
                now = datetime.now(zoneinfo.ZoneInfo(tz_name))
            except Exception:
                now = datetime.now().astimezone()
        else:
            now = datetime.now().astimezone()

    with open(readme_path, "r", encoding="utf-8") as f:
        content = f.read()

    pattern = re.compile(r'<span class="dateTime"(?P<attrs>[^>]*)>(?P<content>[^<]+)</span>')
    offsets = [0, 15, 37, 65]
    match_count = 0

    def repl(m):
        nonlocal match_count
        idx = match_count
        match_count += 1
        sec = offsets[idx] if idx < len(offsets) else offsets[-1] + (idx - len(offsets) + 1) * 30
        dt = now + timedelta(seconds=sec)
        epoch = int(dt.timestamp())
        formatted = dt.strftime("%m/%d/%y(%a)%H:%M:%S")
        attrs = m.group("attrs")
        if "data-utc=" in attrs:
            new_attrs = re.sub(r'data-utc=["\']?\d+["\']?', f'data-utc="{epoch}"', attrs)
            return f'<span class="dateTime"{new_attrs}>{formatted}</span>'
        return f'<span class="dateTime"{attrs}>{formatted}</span>'

    new_content = pattern.sub(repl, content)
    if new_content != content:
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return True
    return False


def main():
    default_out = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--login", default=os.environ.get("GH_LOGIN", "thatfrozenfrog"),
                    help="GitHub username (default: thatfrozenfrog)")
    ap.add_argument("--token", default=None, help="GitHub token (default: GITHUB_TOKEN env or gh auth token)")
    ap.add_argument("--out-dir", default=os.environ.get("OUT_DIR", default_out),
                    help="Directory to write SVGs (default: repository root)")
    ap.add_argument("--mock", action="store_true", help="Generate preview stats using mock data (offline test)")
    args = ap.parse_args()

    if args.mock:
        print("Using mock data (--mock specified)...")
        s = mock_summary()
    else:
        token = get_token(args.token)
        if not token:
            print("Notice: No GITHUB_TOKEN found and 'gh auth token' not available.")
            print("Falling back to mock data preview for local test. Provide GITHUB_TOKEN for real stats.")
            s = mock_summary()
        else:
            try:
                s = summarise(fetch(args.login, token))
            except Exception as e:
                print(f"Failed to fetch real stats from GitHub API: {e}")
                print("Falling back to mock data preview...")
                s = mock_summary()

    files = {"stats.svg": draw_stats(s), "streak.svg": draw_streak(s),
             "langs.svg": draw_langs(s), "year.svg": draw_year(s),
             "banned.svg": draw_banned()}
    for word in ("about", "stack", "projects", "stats", "thread", "catalog"):
        files[f"hd-{word.replace(' ', '-')}.svg"] = draw_heading(word)

    changed = [n for n, svg in files.items()
               if write(os.path.join(args.out_dir, n), svg)]

    readme_path = os.path.join(args.out_dir, "README.md")
    if os.path.exists(readme_path) and update_readme_datetimes(readme_path):
        changed.append("README.md")
    lt = s.get("lifetime_total", s["total"])
    print(f"[{args.login}] {lt} lifetime contributions ({s['total']} this year), {s['active']} active days, "
          f"best week {s['best_week']}, current streak "
          f"{s['current']['length']}, longest {s['longest']['length']}")
    print("languages by bytes: "
          + ", ".join(f"{n} {v}" for n, v in s["by_size"]))
    print("updated: " + (", ".join(sorted(changed)) if changed else "nothing"))


if __name__ == "__main__":
    main()
