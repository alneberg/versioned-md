"""GitHub API helper for fetching approved reviewers of a pull request."""

import requests


def fetch_reviewers(pr_number: int, repo: str, token: str) -> list[str]:
    """Query the GitHub API and return a list of GitHub logins for approved reviewers.

    Args:
        pr_number: The numeric pull-request number.
        repo: The repository in ``owner/name`` format.
        token: A GitHub personal-access token or ``GITHUB_TOKEN``.

    Returns:
        A list of login strings, e.g. ``["alice", "bob"]``.
        Returns an empty list if the API call fails.
    """
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}/reviews"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
    except requests.RequestException:
        return []

    # Filter for APPROVED reviews only
    approved = {
        r["user"]["login"]
        for r in resp.json() or []
        if r.get("state") == "APPROVED"
    }
    return sorted(approved)
