from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Scope:
    """A ZenTao product or project scope.

    Args:
        id: ZenTao scope ID.
        name: Display name of the scope.
        kind: Scope kind, either ``product`` or ``project``.
    """

    id: int
    name: str
    kind: str  # "product" 或 "project"


@dataclass(frozen=True)
class ZenTaoClientConfig:
    """Configuration used to access the ZenTao API.

    Args:
        base_url: ZenTao server URL without the API path.
        account: Optional ZenTao account.
        password: Optional ZenTao password.
        token: Optional API token.
    """

    base_url: str
    account: str = ""
    password: str = ""
    token: str = ""


class ZenTaoClient:
    """Minimal asynchronous client for the ZenTao v1 API."""

    def __init__(self, config: ZenTaoClientConfig) -> None:
        """Create a ZenTao client.

        Args:
            config: Client configuration.
        """
        self.config = config
        self._token = config.token
        self._client = httpx.AsyncClient(
            base_url=f"{config.base_url.rstrip('/')}/api.php/v1/",
            headers=self._headers(),
            timeout=30,
        )

    async def __aenter__(self) -> "ZenTaoClient":
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
        """Authenticate with account credentials when no token is configured.

        Raises:
            RuntimeError: If credentials are missing or the response has no token.
        """
        if self._token:
            return
        if not self.config.account or not self.config.password:
            raise RuntimeError("未配置 ZenTao API Token 且无账号密码")

        response = await self._request(
            "POST",
            "tokens",
            json={"account": self.config.account, "password": self.config.password},
        )
        token = response.json().get("token")
        if not token:
            raise RuntimeError("ZenTao Token 响应为空")
        self._token = str(token)
        self._client.headers.update(self._headers())

    async def list_scopes(
        self, product_ids: set[int], project_ids: set[int]
    ) -> list[Scope]:
        """List selected products and projects.

        Args:
            product_ids: Product IDs to retain, or an empty set for all products.
            project_ids: Project IDs to retain, or an empty set for all projects.

        Returns:
            Product and project scopes.

        Raises:
            RuntimeError: If pagination exceeds 100 pages.
        """
        scopes: list[Scope] = []
        scopes.extend(
            Scope(int(item["id"]), f"产品 · {item.get("name") or item["id"]}", "product")
            for item in await self._list_resource("products", "products")
            if not product_ids or int(item["id"]) in product_ids
        )
        scopes.extend(
            Scope(
                int(item["id"]),
                f"项目 · {item.get('name') or item['id']}",
                "project",
            )
            for item in await self._list_resource("projects", "projects")
            if not project_ids or int(item["id"]) in project_ids
        )
        return scopes

    async def list_projects(self) -> list[Scope]:
        """List projects without loading unrelated product scopes.

        Returns:
            All projects visible to the configured ZenTao account.
        """
        return [
            Scope(int(item["id"]), f"项目 · {item.get('name') or item['id']}", "project")
            for item in await self._list_resource("projects", "projects")
        ]

    async def list_users(self) -> dict[str, str]:
        """Return a lookup from ZenTao account names to real names.

        Returns:
            Account-to-real-name mapping for visible users.
        """
        users = await self._list_resource("users", "users")
        return {str(item.get("account")): str(item.get("realname") or item.get("account")) for item in users if item.get("account")}

    async def list_bugs(self, scope: Scope) -> list[dict]:
        """List all bugs in a product or project.

        Args:
            scope: Product or project whose bugs should be listed.

        Returns:
            Raw bug dictionaries returned by ZenTao.

        Raises:
            RuntimeError: If pagination exceeds 100 pages.
        """
        resource = "projects" if scope.kind == "project" else "products"
        return await self._list_resource(
            f"{resource}/{scope.id}/bugs", "bugs", {"status": "all"}
        )

    async def enrich_module_names(self, bugs: list[dict]) -> list[dict]:
        """Fill missing module labels from representative bug detail responses.

        ZenTao list responses often contain only a numeric module ID. One detail
        request per distinct module is enough to recover its display name.

        Args:
            bugs: Bugs returned by a list endpoint.

        Returns:
            The same bug list with available ``moduleTitle`` values filled in.
        """
        representatives: dict[int, int] = {}
        for bug in bugs:
            module_id = self._number(bug.get("module"))
            bug_id = self._number(bug.get("id"))
            label = str(bug.get("moduleTitle") or bug.get("moduleName") or "").strip()
            if module_id > 0 and bug_id > 0 and not label:
                representatives.setdefault(module_id, bug_id)

        names: dict[int, str] = {}
        semaphore = asyncio.Semaphore(6)

        async def load(module_id: int, bug_id: int) -> None:
            async with semaphore:
                try:
                    response = await self._request("GET", f"bugs/{bug_id}")
                    payload = response.json()
                    data = payload.get("data", payload) if isinstance(payload, dict) else {}
                    if isinstance(data, dict):
                        name = str(data.get("moduleTitle") or data.get("moduleName") or "").strip()
                        if name:
                            names[module_id] = name
                except (httpx.HTTPError, ValueError):
                    return

        await asyncio.gather(*(load(module_id, bug_id) for module_id, bug_id in representatives.items()))
        for bug in bugs:
            module_id = self._number(bug.get("module"))
            if module_id in names and not str(bug.get("moduleTitle") or bug.get("moduleName") or "").strip():
                bug["moduleTitle"] = names[module_id]
        return bugs

    def health(self) -> dict:
        """Return the currently configured authentication mode.

        Returns:
            A dictionary containing ``auth`` with ``token``, ``account``, or ``none``.
        """
        if self._token:
            auth = "token"
        elif self.config.account and self.config.password:
            auth = "account"
        else:
            auth = "none"
        return {"auth": auth}

    def auth_configured(self) -> bool:
        """Return whether token or complete account credentials are configured.

        Returns:
            ``True`` when authentication can be attempted.
        """
        return bool(self._token or (self.config.account and self.config.password))

    def _headers(self) -> dict[str, str]:
        return {"Token": self._token} if self._token else {}

    @staticmethod
    def _number(value: object) -> int:
        """Convert an API identifier to an integer safely.

        Args:
            value: Raw identifier from the API response.

        Returns:
            A positive integer or zero for invalid values.
        """
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        response = await self._client.request(method, path, **kwargs)
        response.raise_for_status()
        return response

    async def _list_resource(
        self,
        path: str,
        resource_name: str,
        extra_params: dict[str, Any] | None = None,
    ) -> list[dict]:
        items: list[dict] = []
        params = dict(extra_params or {})
        limit = 100

        for page in range(1, 101):
            page_params = {**params, "page": page, "limit": limit}
            response = await self._request("GET", path, params=page_params)
            payload = response.json()
            page_items, total = self._page_data(payload, resource_name)
            items.extend(page_items)
            if not page_items or len(items) >= total or len(page_items) < limit:
                return items

        raise RuntimeError("ZenTao 分页超过 100 页")

    @staticmethod
    def _page_data(payload: Any, resource_name: str) -> tuple[list[dict], int]:
        data = payload.get("data", {}) if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}
        source = payload if isinstance(payload, dict) else {}
        page_items = source.get("items", source.get(resource_name, data.get("items", data.get(resource_name, []))))
        total = source.get("total", data.get("total", 0))
        if not total and isinstance(source.get("pager"), dict):
            total = source["pager"].get("recTotal", 0)
        return list(page_items or []), int(total or 0)
