import os
import re
import requests


USERNAME = "ethnmz"

def get_stats():
    # Fetch user data
    user_url = f"https://api.github.com/users/{USERNAME}"
    user_data = requests.get(user_url).json()
    followers = user_data.get("followers", 0)
    repos = user_data.get("public_repos", 0)

    # Fetch stars
    repos_url = f"https://api.github.com/users/{USERNAME}/repos?per_page=100"
    repos_data = requests.get(repos_url).json()
    stars = sum(repo.get("stargazers_count", 0) for repo in repos_data if isinstance(repo, dict))

    # Format the text layout
    # (Note: Commits and Lines of Code require advanced API permissions to count across all repos, 
    # so they are set as placeholders here. Repos, Stars, and Followers will update automatically!)
    stats_text = f"""- GitHub Stats ----------------------------------------------------------------
· Repos: .... {repos:<2} {{Contributed: XX}} | Stars: ....................... {stars:<3}
· Commits: ................... XXXX | Followers: ................... {followers:<2}
· Lines of Code: ........... XXXXXX ( XXXXXX++,     XXXXXX-- )"""
    return stats_text

def update_readme(stats_text):
    with open("README.md", "r", encoding="utf-8") as f:
        readme = f.read()

    # Replace the text between the hidden markers
    readme = re.sub(
        r"(?<=<!-- START_STATS -->\n).*?(?=\n<!-- END_STATS -->)",
        stats_text + "\n",
        readme,
        flags=re.DOTALL
    )

    with open("README.md", "w", encoding="utf-8") as f:
        f.write(readme)

if __name__ == "__main__":
    stats = get_stats()
    update_readme(stats)
