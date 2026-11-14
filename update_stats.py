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

WIDTH = 48  # characters per column; the card has two columns side by side
GAP = 5  # characters between the columns

# GitHub's own Primer colors, so the card sits naturally on the profile page
THEMES = {
    "light": {"bg": "#f6f8fa", "edge": "#d0d7de", "key": "#0969da", "val": "#1f2328", "dots": "#afb8c1", "add": "#1a7f37", "del": "#cf222e"},
    "dark": {"bg": "#161b22", "edge": "#30363d", "key": "#58a6ff", "val": "#e6edf3", "dots": "#3d444d", "add": "#3fb950", "del": "#f85149"},
}


def esc(s):
    return html.escape(str(s), quote=False)


def header(title):
    return [("header", title + " " + "-" * (WIDTH - len(title) - 1))]


def field(key, value, color=None):
    """One "· key: ..... value" line, wrapping a long comma list onto right-aligned lines below."""
    value = str(value)
    room = WIDTH - len(key) - 7  # leaves at least two dots
    chunks, parts = [], value.split(", ")
    current = parts[0]
    for k, part in enumerate(parts[1:], start=2):
        limit = room if not chunks else WIDTH - 2
        comma = 1 if k < len(parts) else 0  # a line that wraps ends with a comma
        if len(current) + 2 + len(part) + comma <= limit:
            current += ", " + part
        else:
            chunks.append(current + ",")
            current = part
    chunks.append(current)
    first = chunks[0]
    out = [("field", key, "." * (WIDTH - 5 - len(key) - len(first)), first, color)]
    for rest in chunks[1:]:
        out.append(("cont", " " * (WIDTH - len(rest)) + rest, color))
    return out


def card_columns(s):
    lines = []
    lines += header(f"{USERNAME}@ethnmz.com")
    lines += field("OS", "Windows, Linux, macOS")
    lines += field("Uptime", uptime())
    lines += field("Host", "Texas A&M University")
    lines += field("Role", "Student")
    lines += field("IDE", "VSCode, Antigravity, Cursor")
    lines.append(("blank",))
    lines += header("- Languages")
    lines += field("Programming", "Python, JavaScript, TypeScript, C++, Java")
    lines += field("Markup", "HTML, CSS, JSON, Markdown, YAML")
    lines += field("Spoken", "English, Spanish")
    lines.append(("blank",))
    lines += header("- Hobbies")
    lines += field("Software", "Open Source, Web Dev, Learning AI")
    lines += field("Hardware", "Networking, Homelabbing")

    left, lines = lines, []
    lines += header("- Contact")
    lines += field("Website", "ethnmz.com")
    lines += field("Email.Personal", "ethanmeza43@gmail.com")
    lines += field("Email.Work", "ethan7714@tamu.edu")
    lines += field("LinkedIn", "ethnmz")
    lines += field("Discord", "ethnmz")
    lines.append(("blank",))
    lines += header("- GitHub Stats")
    lines += field("Repos", s["repos"])
    lines += field("Contributed", s["contributed"])
    lines += field("Stars", s["stars"])
    lines += field("Commits", f"{s['commits']:,}")
    lines += field("Followers", s["followers"])
    lines += field("Lines of Code", f"{s['loc_add'] - s['loc_del']:,}")
    lines += field("Added", f"{s['loc_add']:,}++", "add")
    lines += field("Deleted", f"{s['loc_del']:,}--", "del")
    return left, lines


def render(columns, t):
    fs, lh, ch = 16, 22, 9.65
    pad, top = 30, 42
    height = top + lh * max(len(c) for c in columns) + 22
    width = pad * 2 + int((WIDTH * len(columns) + GAP * (len(columns) - 1)) * ch)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
           f'font-family="ConsolasFallback, Consolas, \'JetBrains Mono\', ui-monospace, monospace" font-size="{fs}">',
           f'<rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="6" fill="{t["bg"]}" stroke="{t["edge"]}" stroke-width="2"/>',
           f'<text x="{pad}" y="{top}" xml:space="preserve" fill="{t["val"]}">']
    rows = [(n, i, line) for n, col in enumerate(columns) for i, line in enumerate(col)]
    for n, i, line in rows:
        text_x = pad + round(n * (WIDTH + GAP) * ch)
        y = top + i * lh
        kind = line[0]
        if kind == "blank":
            continue
        if kind == "header":
            out.append(f'<tspan x="{text_x}" y="{y}" fill="{t["key"]}" font-weight="bold">{esc(line[1])}</tspan>')
        elif kind == "field":
            _, key, dots, value, color = line
            val = f'<tspan fill="{t[color]}">{esc(value)}</tspan>' if color else esc(value)
            out.append(f'<tspan x="{text_x}" y="{y}"><tspan fill="{t["dots"]}">· </tspan><tspan fill="{t["key"]}">{esc(key)}</tspan>: '
                       f'<tspan fill="{t["dots"]}">{dots}</tspan> {val}</tspan>')
        elif kind == "cont":
            _, text, color = line
            fill = f' fill="{t[color]}"' if color else ""
            out.append(f'<tspan x="{text_x}" y="{y}"{fill}>{esc(text)}</tspan>')
    out.append("</text></svg>")
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    stats = get_stats()
    columns = card_columns(stats)
    for name, theme in THEMES.items():
        with open(f"{name}_mode.svg", "w", encoding="utf-8") as f:
            f.write(render(columns, theme))
    print(stats)
