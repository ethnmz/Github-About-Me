"""Redraws the neofetch-style profile card (light_mode.svg + dark_mode.svg) with live GitHub stats.

Runs daily from .github/workflows/update.yml. Needs a GITHUB_TOKEN in the environment.
"""
import datetime as dt
import html
import os
import time

import requests

USERNAME = "ethnmz"
BIRTHDAY = dt.date(2006, 9, 23)  # drives the "Uptime" line

API = "https://api.github.com"
BULK_WEEK = 20000
HEADERS = {"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"}


# ---------- stats ----------

def gql(query, variables=None):
    r = requests.post(f"{API}/graphql", json={"query": query, "variables": variables or {}}, headers=HEADERS, timeout=30)
    r.raise_for_status()
    body = r.json()
    if "errors" in body:
        raise RuntimeError(body["errors"])
    return body["data"]


def owned_repos():
    repos, page = [], 1
    while True:
        r = requests.get(f"{API}/users/{USERNAME}/repos", params={"per_page": 100, "page": page, "type": "owner"}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        batch = r.json()
        repos += batch
        if len(batch) < 100:
            return [x for x in repos if not x["fork"]]
        page += 1


def total_commits(created):
    # contribution counts are only available one year at a time
    total, start = 0, created
    now = dt.datetime.now(dt.timezone.utc)
    while start < now:
        end = min(start + dt.timedelta(days=365), now)
        data = gql("""query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) { contributionsCollection(from: $from, to: $to) {
            totalCommitContributions restrictedContributionsCount } } }""",
                   {"login": USERNAME, "from": start.isoformat(), "to": end.isoformat()})
        c = data["user"]["contributionsCollection"]
        total += c["totalCommitContributions"]
        start = end
    return total


def lines_of_code(repo_names):
    # GitHub computes contributor stats lazily and answers 202 until they're ready
    added = deleted = 0
    for full_name in repo_names:
        for _ in range(8):
            r = requests.get(f"{API}/repos/{full_name}/stats/contributors", headers=HEADERS, timeout=30)
            if r.status_code == 202:
                time.sleep(3)
                continue
            if r.status_code == 200 and isinstance(r.json(), list):
                for person in r.json():
                    if (person.get("author") or {}).get("login", "").lower() == USERNAME.lower():
                        # weeks that add or delete tens of thousands of lines are committed dependencies or
                        # generated files (node_modules and friends), not code anyone wrote, so they're skipped
                        weeks = [w for w in person["weeks"] if w["a"] <= BULK_WEEK and w["d"] <= BULK_WEEK]
                        added += sum(w["a"] for w in weeks)
                        deleted += sum(w["d"] for w in weeks)
            break
    return added, deleted


def get_stats():
    user = requests.get(f"{API}/users/{USERNAME}", headers=HEADERS, timeout=30).json()
    repos = owned_repos()
    data = gql("""query($login: String!) { user(login: $login) {
      repositoriesContributedTo(first: 100, includeUserRepositories: false,
        contributionTypes: [COMMIT, PULL_REQUEST, REPOSITORY, PULL_REQUEST_REVIEW]) {
        totalCount nodes { nameWithOwner } } } }""", {"login": USERNAME})
    contributed = data["user"]["repositoriesContributedTo"]
    created = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    added, deleted = lines_of_code([r["full_name"] for r in repos] + [n["nameWithOwner"] for n in contributed["nodes"]])
    return {
        "repos": len(repos),
        "contributed": contributed["totalCount"],
        "stars": sum(r["stargazers_count"] for r in repos),
        "followers": user["followers"],
        "commits": total_commits(created),
        "loc_add": added,
        "loc_del": deleted,
    }


def uptime(today=None):
    today = today or dt.date.today()
    years = today.year - BIRTHDAY.year - ((today.month, today.day) < (BIRTHDAY.month, BIRTHDAY.day))
    last = BIRTHDAY.replace(year=BIRTHDAY.year + years)
    months = (today.year - last.year) * 12 + today.month - last.month - (today.day < last.day)
    anchor_month = (last.month - 1 + months) % 12 + 1
    anchor_year = last.year + (last.month - 1 + months) // 12
    anchor = dt.date(anchor_year, anchor_month, min(last.day, 28 if anchor_month == 2 else 30 if anchor_month in (4, 6, 9, 11) else 31))
    days = (today - anchor).days

    def plural(n, word):
        return f"{n} {word}{'' if n == 1 else 's'}"
    return f"{plural(years, 'year')}, {plural(months, 'month')}, {plural(days, 'day')}"


# ---------- the card ----------

WIDTH = 70  # characters per text line

# colors from the profile picture: an overcast sky, forested hills, and a cat with green eyes
# and orange ears
THEMES = {
    "light": {"bg": "#e4e6e2", "edge": "#b7bcb5", "key": "#3f6233", "val": "#2b2a2a", "dots": "#b3b9b0", "add": "#5c8f3a", "del": "#c46a3c"},
    "dark": {"bg": "#1d241d", "edge": "#384435", "key": "#9ccb78", "val": "#dfe2dc", "dots": "#3b4738", "add": "#9ccb78", "del": "#e8945f"},
}

def esc(s):
    return html.escape(str(s), quote=False)


def header(title):
    return [("header", title + " " + "-" * (WIDTH - len(title) - 1))]


def field(key, value):
    dots = WIDTH - len(key) - len(str(value)) - 6
    return [("field", key, "." * max(dots, 1), value)]


def card_lines(s):
    lines = []
    lines += header(f"{USERNAME}@ethnmz.com")
    lines += field("OS", "Windows, Linux, macOS")
    lines += field("Uptime", uptime())
    lines += field("Host", "Texas A&M University")
    lines += field("Role", "Student")
    lines += field("IDE", "VSCode, Antigravity, Cursor")
    lines.append(("blank",))
    lines += field("Languages.Programming", "Python, JavaScript, TypeScript, C++, Java")
    lines += field("Languages.Markup", "HTML, CSS, JSON, Markdown, YAML")
    lines += field("Languages.Spoken", "English, Spanish")
    lines.append(("blank",))
    lines += field("Hobbies.Software", "Open Source, Web Dev, Learning AI")
    lines += field("Hobbies.Hardware", "Networking, Homelabbing")
    lines.append(("blank",))
    lines += header("- Contact")
    lines += field("Website", "ethnmz.com")
    lines += field("Email.Personal", "ethanmeza43@gmail.com")
    lines += field("Email.Work", "ethan7714@tamu.edu")
    lines += field("LinkedIn", "ethnmz")
    lines += field("Discord", "ethnmz")
    lines.append(("blank",))
    lines += header("- GitHub Stats")
    lines.append(("pair", ("Repos", f"{s['repos']} {{Contributed: {s['contributed']}}}"), ("Stars", s["stars"])))
    lines.append(("pair", ("Commits", f"{s['commits']:,}"), ("Followers", s["followers"])))
    lines.append(("loc", f"{s['loc_add'] - s['loc_del']:,}", f"{s['loc_add']:,}", f"{s['loc_del']:,}"))
    return lines


def render(lines, t):
    fs, lh = 16, 21
    text_x, top = 36, 44
    height = top + lh * len(lines) + 28
    width = text_x + int(WIDTH * 9.7) + 40
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="ConsolasFallback, Consolas, \'JetBrains Mono\', ui-monospace, monospace" font-size="{fs}">',
           f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" fill="{t["bg"]}" stroke="{t["edge"]}" stroke-width="2"/>',
           f'<text x="{text_x}" y="{top}" xml:space="preserve" fill="{t["val"]}">']
    for i, line in enumerate(lines):
        y = top + i * lh
        kind = line[0]
        if kind == "blank":
            continue
        if kind == "header":
            out.append(f'<tspan x="{text_x}" y="{y}" fill="{t["key"]}" font-weight="bold">{esc(line[1])}</tspan>')
        elif kind == "field":
            _, key, dots, value = line
            out.append(f'<tspan x="{text_x}" y="{y}"><tspan fill="{t["dots"]}">· </tspan><tspan fill="{t["key"]}">{esc(key)}</tspan>: '
                       f'<tspan fill="{t["dots"]}">{dots}</tspan> {esc(value)}</tspan>')
        elif kind == "pair":
            (k1, v1), (k2, v2) = line[1], line[2]
            half = WIDTH // 2 + 2
            d1 = "." * max(1, half - len(k1) - len(str(v1)) - 7)
            d2 = "." * max(1, WIDTH - half - len(k2) - len(str(v2)) - 7)
            out.append(f'<tspan x="{text_x}" y="{y}"><tspan fill="{t["dots"]}">· </tspan><tspan fill="{t["key"]}">{k1}</tspan>: '
                       f'<tspan fill="{t["dots"]}">{d1}</tspan> {esc(v1)} <tspan fill="{t["dots"]}">|</tspan> '
                       f'<tspan fill="{t["key"]}">{k2}</tspan>: <tspan fill="{t["dots"]}">{d2}</tspan> {esc(v2)}</tspan>')
        elif kind == "loc":
            _, net, add, rem = line
            dots = "." * max(1, WIDTH - len("Lines of Code") - len(net) - len(add) - len(rem) - 16)
            out.append(f'<tspan x="{text_x}" y="{y}"><tspan fill="{t["dots"]}">· </tspan><tspan fill="{t["key"]}">Lines of Code</tspan>: '
                       f'<tspan fill="{t["dots"]}">{dots}</tspan> {net} ( <tspan fill="{t["add"]}">{add}++</tspan>, '
                       f'<tspan fill="{t["del"]}">{rem}--</tspan> )</tspan>')
    out.append("</text></svg>")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    stats = get_stats()
    lines = card_lines(stats)
    for name, theme in THEMES.items():
        with open(f"{name}_mode.svg", "w", encoding="utf-8") as f:
            f.write(render(lines, theme))
    print(stats)
