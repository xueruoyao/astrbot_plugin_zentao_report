from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Scope:
    """A reportable project scope.

    Args:
        id: Project identifier (Huly project string identifier, e.g. ``5092``).
        name: Display name of the scope.
        kind: Scope kind; kept for compatibility, always ``project``.
    """

    id: str
    name: str
    kind: str = "project"


@dataclass(frozen=True)
class BridgeClientConfig:
    """Configuration used to reach the Huly bridge sidecar.

    Args:
        base_url: Bridge base URL, e.g. ``http://127.0.0.1:8600``.
        token: Optional shared secret matching the bridge ``BRIDGE_TOKEN``.
    """

    base_url: str
    token: str = ""


class HulyClient:
    """Asynchronous client for the Huly bridge sidecar.

    The bridge normalizes Huly data into the same field shape the report
    layer already consumes (``id/title/status/severity/pri/...``), so the
    aggregation and rendering code is source-agnostic.
    """

    def __init__(self, config: BridgeClientConfig) -> None:
        """Create a bridge client.

        Args:
            config: Client configuration.
        """
        self.config = config
        self._client = httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"),
            headers={"X-Bridge-Token": config.token} if config.token else {},
            timeout=30,
        )

    async def __aenter__(self) -> "HulyClient":
        """Open the underlying HTTP client.

        Returns:
            This client instance.
        """
        await self._client.__aenter__()
        return self

    async def __aexit__(self, *exc) -> None:
        """Close the underlying HTTP client.

        Args:
            *exc: Context manager exception information.
        """
        await self._client.__aexit__(*exc)

    async def authenticate(self) -> None:
        """Verify bridge connectivity and auth readiness.

        The bridge holds the Huly credentials; the plugin only needs the
        bridge to be reachable and authorized.

        Raises:
            RuntimeError: If the bridge is unreachable or reports a failure.
        """
        try:
            response = await self._request("GET", "/health")
            payload = response.json()
            if not payload.get("ok"):
                raise RuntimeError("Huly Bridge 未就绪")
        except httpx.HTTPError as exc:
            raise RuntimeError(f"无法连接 Huly Bridge：{exc}") from exc

    async def list_scopes(
        self, product_ids: set[str], project_ids: set[str]
    ) -> list[Scope]:
        """List selected projects.

        Huly has no separate product concept, so only ``project_ids`` is
        honored; ``product_ids`` is accepted for interface compatibility.

        Args:
            product_ids: Unused, kept for signature compatibility.
            project_ids: Project identifiers to retain, or empty for all.

        Returns:
            Project scopes.
        """
        items = await self._request("GET", "/projects")
        projects = items.json()
        return [
            Scope(str(p["id"]), f"项目 · {p.get('name') or p['id']}", "project")
            for p in projects
            if not project_ids or str(p["id"]) in project_ids
        ]

    async def list_projects(self) -> list[Scope]:
        """List all projects.

        Returns:
            All projects visible to the bridge's Huly account.
        """
        return await self.list_scopes(set(), set())

    async def list_users(self) -> dict[str, str]:
        """Return a lookup from Huly account identifiers to real names.

        Returns:
            Account-to-real-name mapping.
        """
        response = await self._request("GET", "/users")
        return {str(k): str(v) for k, v in response.json().items()}

    async def list_bugs(self, scope: Scope) -> list[dict]:
        """List all bugs in a project, normalized to the report field shape.

        Args:
            scope: Project whose bugs should be listed.

        Returns:
            Bug dictionaries with the normalized report field names.
        """
        from urllib.parse import quote

        response = await self._request("GET", f"/projects/{quote(str(scope.id), safe='')}/bugs")
        return list(response.json())

    async def enrich_module_names(self, bugs: list[dict]) -> list[dict]:
        """Return bugs unchanged; the bridge already supplies module names.

        Args:
            bugs: Bugs returned by ``list_bugs``.

        Returns:
            The same bug list.
        """
        return bugs

    def health(self) -> dict:
        """Return the configured authentication mode for the bridge.

        Returns:
            A dictionary containing ``auth`` with ``token`` or ``none``.
        """
        return {"auth": "token" if self.config.token else "none"}

    def auth_configured(self) -> bool:
        """Return whether the bridge URL is configured.

        Returns:
            ``True`` when a bridge URL is present.
        """
        return bool(self.config.base_url)

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response
