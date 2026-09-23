from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx


class OpenClawError(RuntimeError):
    pass


class OpenClawClient:
    """OpenClaw Gateway HTTP client.

    Uses the Gateway's official OpenResponses endpoint instead of invoking a local
    `openclaw` executable. This keeps OpenClaw on the Windows host while OpsSwarm
    can run inside Docker.
    """

    def __init__(self, base_url: str | None = None, token: str | None = None, timeout: int = 600):
        self.base_url = (base_url or os.getenv("OPSWARM_OPENCLAW_GATEWAY_URL") or os.getenv("OPSSWARM_OPENCLAW_GATEWAY_URL") or "http://127.0.0.1:18789").rstrip("/")
        self.token = token if token is not None else os.getenv("OPENCLAW_GATEWAY_TOKEN", "")
        self.timeout = timeout
        self.client = httpx.AsyncClient(base_url=self.base_url, timeout=httpx.Timeout(timeout + 30.0))

    @staticmethod
    def _agent_session_key(agent: str, session_key: str) -> str:
        # OpenClaw 2026.9.x requires an explicit owner when multiple agents exist.
        # An agent-scoped session key is accepted by both the Gateway and CLI path.
        if session_key.startswith("agent:"):
            return session_key
        return f"agent:{agent}:{session_key}"

    def _headers(self, agent: str, session_key: str) -> dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "x-openclaw-agent-id": agent,
            "x-openclaw-session-key": self._agent_session_key(agent, session_key),
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def health(self) -> dict[str, Any]:
        try:
            r = await self.client.get("/v1/models", headers=self._headers("main", "opsswarm-health"), timeout=10.0)
            ok = r.is_success
            agents = []
            if ok:
                try:
                    agents = [x.get("id") for x in (r.json().get("data") or []) if isinstance(x, dict)]
                except Exception:
                    agents = []
            return {"ok": ok, "status_code": r.status_code, "gateway_url": self.base_url, "agent_targets": agents}
        except Exception as exc:
            return {"ok": False, "gateway_url": self.base_url, "error_type": type(exc).__name__, "error": str(exc)}

    async def run_text(self, agent: str, session_key: str, prompt: str) -> str:
        if not self.token:
            raise OpenClawError("OPENCLAW_GATEWAY_TOKEN is not configured")
        try:
            r = await self.client.post(
                "/v1/responses",
                headers=self._headers(agent, session_key),
                json={"model": "openclaw", "input": prompt, "stream": False},
            )
        except Exception as exc:
            raise OpenClawError(f"OpenClaw Gateway request failed: {type(exc).__name__}: {exc}") from exc
        if not r.is_success:
            message = r.text[-1600:]
            raise OpenClawError(f"OpenClaw Gateway HTTP {r.status_code}: {message}")
        try:
            envelope = r.json()
        except Exception as exc:
            raise OpenClawError(f"OpenClaw Gateway returned non-JSON response: {r.text[-800:]}") from exc
        if envelope.get("status") in {"failed", "incomplete"}:
            raise OpenClawError(f"OpenClaw run {envelope.get('status')}: {json.dumps(envelope.get('error') or envelope.get('incomplete_details'), default=str)}")
        if isinstance(envelope.get("output_text"), str) and envelope["output_text"].strip():
            return envelope["output_text"]
        texts: list[str] = []
        for item in envelope.get("output", []) if isinstance(envelope.get("output"), list) else []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if isinstance(content, dict) and isinstance(content.get("text"), str):
                    texts.append(content["text"])
        if texts:
            return "\n".join(texts)
        raise OpenClawError("No assistant text in OpenClaw OpenResponses envelope")

    @staticmethod
    def _extract_json(text: str) -> Any:
        s = text.strip()
        if s.startswith("```"):
            s = re.sub(r"^```(?:json)?\s*", "", s)
            s = re.sub(r"\s*```$", "", s)
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            starts = [i for i in (s.find("{"), s.find("[")) if i >= 0]
            if not starts:
                raise
            start = min(starts)
            closing = "}" if s[start] == "{" else "]"
            end = s.rfind(closing)
            if end < start:
                raise
            return json.loads(s[start : end + 1])

    async def run_json(self, agent: str, session_key: str, prompt: str) -> Any:
        return self._extract_json(await self.run_text(agent, session_key, prompt))
