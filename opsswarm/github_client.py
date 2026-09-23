from __future__ import annotations

from typing import Any
import httpx


class GitHubClient:
    def __init__(self, token: str, repo: str, base_url: str = "https://api.github.com"):
        self.repo = repo
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def _req(self, method: str, path: str, **kwargs) -> Any:
        r = await self.client.request(method, path, **kwargs)
        r.raise_for_status()
        return r.json() if r.content else None

    async def get_issue(self, number: int):
        return await self._req("GET", f"/repos/{self.repo}/issues/{number}")

    async def list_issues(self, state: str = "open", labels: list[str] | None = None, per_page: int = 50):
        if state not in {"open", "closed", "all"}:
            raise ValueError(f"unsupported issue state filter: {state}")
        params: dict[str, Any] = {"state": state, "per_page": per_page, "sort": "created", "direction": "desc"}
        if labels:
            params["labels"] = ",".join(labels)
        return await self._req("GET", f"/repos/{self.repo}/issues", params=params)

    async def list_open_issues(self, labels: list[str] | None = None, per_page: int = 50):
        return await self.list_issues("open", labels, per_page)

    async def comment(self, number: int, body: str):
        return await self._req("POST", f"/repos/{self.repo}/issues/{number}/comments", json={"body": body})

    async def list_issue_comments(self, number: int, per_page: int = 50):
        return await self._req(
            "GET",
            f"/repos/{self.repo}/issues/{number}/comments",
            params={"per_page": per_page, "sort": "created", "direction": "asc"},
        )

    async def set_labels(self, number: int, labels: list[str]):
        return await self._req("POST", f"/repos/{self.repo}/issues/{number}/labels", json={"labels": labels})

    async def replace_labels(self, number: int, labels: list[str]):
        """Replace the complete issue label set so lifecycle state remains canonical."""
        return await self._req("PUT", f"/repos/{self.repo}/issues/{number}/labels", json={"labels": labels})

    async def close_issue(self, number: int):
        return await self._req("PATCH", f"/repos/{self.repo}/issues/{number}", json={"state": "closed", "state_reason": "completed"})

    async def reopen_issue(self, number: int):
        return await self._req("PATCH", f"/repos/{self.repo}/issues/{number}", json={"state": "open"})

    async def create_issue(self, title: str, body: str, labels: list[str] | None = None):
        payload: dict[str, Any] = {"title": title, "body": body}
        if labels:
            payload["labels"] = labels
        return await self._req("POST", f"/repos/{self.repo}/issues", json=payload)

    async def permission(self, username: str) -> str:
        data = await self._req("GET", f"/repos/{self.repo}/collaborators/{username}/permission")
        return data.get("permission", "none")
