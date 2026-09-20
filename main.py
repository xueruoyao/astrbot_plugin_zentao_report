"""ZenTao daily bug report plugin."""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import tempfile
from typing import Any

import httpx

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, MessageChain, filter
from astrbot.api.star import Context, Star

if __package__:
    from .data_scope import BridgeClientConfig, HulyClient, Scope
    from .report_html import STYLES
    from .report_logic import (
        build_report,
        build_review_items,
        build_rule_summary,
        parse_ids,
        parse_push_targets,
    )
    from .report_renderer import render_report_png
else:
    from data_scope import BridgeClientConfig, HulyClient, Scope
    from report_html import STYLES
    from report_logic import (
        build_report,
        build_review_items,
        build_rule_summary,
        parse_ids,
        parse_push_targets,
    )
    from report_renderer import render_report_png


class ZenTaoReport(Star):
    """Huly 每日缺陷日报：只读生成手机比例图片，可配置主动推送到企业微信。"""

    def __init__(self, context: Context, config: AstrBotConfig) -> None:
        super().__init__(context)
        self.config = config

    def _client(self) -> HulyClient:
        """Build a Huly bridge client from the plugin configuration.

        Returns:
            A client for the Huly bridge sidecar.
        """
        return HulyClient(
            BridgeClientConfig(
                base_url=str(self.config.get("huly_bridge_url", "")).strip(),
                token=str(self.config.get("huly_bridge_token", "")).strip(),
            )
        )

    def _auth_summary(self, client: HulyClient) -> str:
        """Summarize bridge readiness without exposing secrets.

        Args:
            client: Huly bridge client.

        Returns:
            A redacted authentication state string.
        """
        if not client.auth_configured():
            return "未配置 Bridge 地址"
        mode = client.health()["auth"]
        return {"token": "Bridge Token 已配置", "none": "Bridge 无鉴权（直连）"}[mode]

    def _style(self, requested: str = "") -> str:
        """Resolve the report style from a request or plugin config.

        Args:
            requested: Optional style override from a command.

        Returns:
            A valid style key from ``STYLES``.
        """
        chosen = (requested.strip().lower() or str(self.config.get("report_style", "graphite")).strip().lower() or "graphite")
        return chosen if chosen in STYLES else "graphite"

    async def _collect(self) -> tuple[list[Scope], dict[str, list[dict[str, Any]]]]:
        """Authenticate and collect scopes and their bugs.

        Returns:
            A tuple of scopes and bugs grouped by scope ID.
        """
        project_ids = parse_ids(str(self.config.get("scope_project_ids", "")))

        client = self._client()
        async with client:
            await client.authenticate()
            scopes = await client.list_scopes(set(), project_ids)
            bugs_by_scope: dict[str, list[dict[str, Any]]] = {}
            for scope in scopes:
                bugs = await client.list_bugs(scope)
                bugs_by_scope[scope.id] = await client.enrich_module_names(bugs)
        return scopes, bugs_by_scope

    async def _collect_project(self, query: str) -> tuple[list[Scope], dict[str, list[dict[str, Any]]], dict[str, str]]:
        """Load exactly one project by its identifier or display name.

        Args:
            query: Project identifier (e.g. ``5092``) or project name.

        Returns:
            The matched project and its bugs.

        Raises:
            RuntimeError: If no project uniquely matches the query.
        """
        query = query.strip()
        if not query:
            raise RuntimeError("请提供项目标识或项目名称，例如 /BR 5092")
        client = self._client()
        async with client:
            await client.authenticate()
            projects = await client.list_scopes(set(), set())
            # Exact identifier wins; otherwise try exact then prefix name match.
            exact_id = [scope for scope in projects if query == str(scope.id)]
            display = lambda s: s.name.removeprefix("项目 · ")
            exact_name = [scope for scope in projects if query == display(scope)]
            prefix_matches = [scope for scope in projects if display(scope).startswith(query) or str(scope.id).startswith(query)]
            candidates = exact_id or list(dict.fromkeys(exact_name + prefix_matches))
            if len(candidates) > 1 or (exact_name and prefix_matches and exact_name[0] not in prefix_matches):
                candidates = list(dict.fromkeys(exact_name + prefix_matches))
                bug_lists = await asyncio.gather(*(client.list_bugs(scope) for scope in candidates))
                candidates = [scope for scope, bugs in zip(candidates, bug_lists) if bugs] or candidates
            if len(candidates) != 1:
                labels = ", ".join(f"{scope.id}:{scope.name}" for scope in candidates)
                raise RuntimeError(f"标识「{query}」匹配多个项目：{labels or '无'}")
            matched = candidates
            bugs, users = await asyncio.gather(client.list_bugs(matched[0]), client.list_users())
            return matched, {matched[0].id: await client.enrich_module_names(bugs)}, users

    def _render_path(self, report: dict[str, Any], style: str) -> str:
        """Render the report context to a local PNG file.

        Args:
            report: Aggregated report context.
            style: One of the style keys in ``STYLES``.

        Returns:
            The local PNG file path.
        """
        output_dir = os.path.abspath(os.path.join("data", "temp"))
        os.makedirs(output_dir, exist_ok=True)
        temp = tempfile.NamedTemporaryFile(prefix="zentao_report_", suffix=".png", dir=output_dir, delete=False)
        temp.close()
        try:
            return render_report_png(report, temp.name, style)
        except Exception:
            os.unlink(temp.name)
            raise

    async def _to_thread_render(self, report: dict[str, Any], style: str) -> str:
        """Run the blocking Playwright render in a worker thread.

        Args:
            report: Aggregated report context.
            style: One of the style keys in ``STYLES``.

        Returns:
            The local PNG file path.
        """
        import asyncio

        return await asyncio.to_thread(self._render_path, report, style)

    async def _build_report_context(self) -> tuple[list[Scope], dict[str, list[dict[str, Any]]], dict[str, Any]]:
        """Collect scopes and bugs and aggregate a report context.

        Returns:
            Scopes, bugs, and the aggregated report context.
        """
        scopes, bugs_by_scope = await self._collect()
        generated_at = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
        report = build_report(
            scopes,
            bugs_by_scope,
            str(self.config.get("report_title", "Huly 每日缺陷日报")).strip() or "Huly 每日缺陷日报",
            generated_at,
        )
        return scopes, bugs_by_scope, report

    async def _build_project_report_context(self, query: str) -> dict[str, Any]:
        """Build a report context for one selected project.

        Args:
            query: ZenTao project ID or exact name.

        Returns:
            A renderer-ready project report.
        """
        scopes, bugs_by_scope, users = await self._collect_project(query)
        for bug in bugs_by_scope[scopes[0].id]:
            for field in ("openedBy", "resolvedBy", "assignedTo"):
                value = bug.get(field)
                account = value.get("account") if isinstance(value, dict) else value
                if account and str(account) in users:
                    if isinstance(value, dict):
                        value["realname"] = users[str(account)]
                    else:
                        bug[field] = users[str(account)]
        report = build_report(
            scopes,
            bugs_by_scope,
            str(self.config.get("report_title", "Huly 每日缺陷日报")).strip() or "Huly 每日缺陷日报",
            dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
            int(self.config.get("top_bug_limit", 5) or 5),
        )
        report["project_name"] = scopes[0].name.removeprefix("项目 · ")
        report["system_name"] = str(self.config.get("system_name", "Huly")).strip() or "Huly"
        report["project_avatar_url"] = self._project_avatar(report["project_name"])
        return report

    async def _ai_daily_comment(self, event: AstrMessageEvent, report: dict[str, Any]) -> str:
        """Ask the active chat provider for a bounded factual daily comment.

        Args:
            event: Command event that selects the active chat provider.
            report: Project report containing only computed ZenTao metrics.

        Returns:
            A concise AI comment, or the deterministic comment on any failure.
        """
        if not self.config.get("ai_summary_enabled", True):
            return "AI点评未启用"
        context = {
            "project": report["project_name"], "total": report["open_total"] + report["closed_total"],
            "active": report["active_total"], "resolved": report["resolved_total"],
            "closed": report["closed_total"], "high_risk": report["high_risk_total"],
            "today_created": report["opened_today_total"], "today_resolved": report["resolved_today_total"],
            "modules": report["modules"][:8], "top_bugs": report["top_bugs"][:5],
        }
        prompt = (
            "你是研发项目经理。请根据下面的项目日报上下文，生成一段中文状况点评，"
            "长度60至120字，分成2至3句。只能使用上下文事实，不得编造人员、状态、数量或完成情况。"
            "评价今日新增与解决情况，指出积压重点和高风险缺陷；若上下文包含今日解决人及数量可以点名表扬，"
            "没有就不要猜测。不要输出标题、Markdown、免责声明或套话。\n\n"
            + json.dumps(context, ensure_ascii=False)
        )
        try:
            provider_id = str(self.config.get("ai_summary_provider_id", "")).strip()
            if not provider_id:
                provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
            response = await self.context.llm_generate(chat_provider_id=provider_id, prompt=prompt)
            comment = response.completion_text.strip().replace("\n", " ")
            if comment:
                return comment[:240]
        except Exception:  # noqa: BLE001
            logger.warning("AstrBot provider unavailable for daily comment")

        api_key = str(self.config.get("ai_fallback_api_key", "")).strip()
        base_url = str(self.config.get("ai_fallback_base_url", "https://api.openai.com/v1")).strip().rstrip("/")
        model = str(self.config.get("ai_fallback_model", "gpt-4o-mini")).strip()
        if not api_key or not model:
            return "AI点评暂不可用"
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"model": model, "temperature": 0.2, "messages": [{"role": "system", "content": "只根据用户提供的项目事实生成中文研发状况点评。"}, {"role": "user", "content": prompt}]},
                )
                response.raise_for_status()
                payload = response.json()
                comment = str(payload["choices"][0]["message"]["content"]).strip().replace("\n", " ")
                return comment[:240] if comment else "AI点评暂不可用"
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
            logger.warning("Fallback API unavailable for daily comment")
            return "AI点评暂不可用"

    def _project_avatar(self, project_name: str) -> str:
        """Resolve an optional project avatar URL from the JSON configuration.

        Args:
            project_name: ZenTao project name without its display prefix.

        Returns:
            A configured URL or an empty string when no avatar is configured.
        """
        import json

        raw = str(self.config.get("project_avatar_urls", "")).strip()
        if not raw:
            return ""
        try:
            avatars = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("project_avatar_urls must be valid JSON")
            return ""
        return str(avatars.get(project_name, "")).strip() if isinstance(avatars, dict) else ""

    def _push_targets(self) -> list[str]:
        """Resolve the ordered push target sessions from configuration.

        Returns:
            Unique push target UMOs; ``push_sessions`` wins, the legacy
            single ``push_session`` is the fallback.
        """
        return parse_push_targets(
            str(self.config.get("push_sessions", "") or ""),
            str(self.config.get("push_session", "") or ""),
        )

    def _push_interval(self) -> float:
        """Read the pause between consecutive group pushes, in seconds.

        Returns:
            A non-negative delay; defaults to 1 second for ws channels.
        """
        try:
            return max(0.0, float(self.config.get("push_interval_seconds", 1) or 0))
        except (TypeError, ValueError):
            return 1.0

    async def _send_report(self, report: dict[str, Any], style: str) -> bool:
        """Render once and push the report image to every target group in turn.

        The image is generated a single time, then the same file is sent to
        each configured session sequentially with a short pause between
        sends, so one websocket channel is never flooded with images.

        Args:
            report: Aggregated report context.
            style: Style key for rendering.

        Returns:
            True when at least one target accepted the message.
        """
        targets = self._push_targets()
        if not targets:
            raise RuntimeError("未配置推送目标会话，请在 push_sessions 填入多个 /sid（换行或逗号分隔）")
        if not self.config.get("push_enabled"):
            raise RuntimeError("推送开关未开启")

        path = await self._to_thread_render(report, style)
        interval = self._push_interval()
        delivered = 0
        failures: list[str] = []
        for index, session in enumerate(targets):
            if index and interval:
                await asyncio.sleep(interval)
            try:
                chain = MessageChain().message(f"Huly 日报 {report['generated_at']}").file_image(path)
                if await self.context.send_message(session, chain):
                    delivered += 1
                else:
                    failures.append(session)
            except Exception as exc:  # noqa: BLE001
                failures.append(session)
                logger.warning("Push to session %s failed: %s", session, exc)
        if delivered:
            if failures:
                logger.warning("Pushed to %d/%d sessions; failed: %s", delivered, len(targets), ", ".join(failures))
            return True
        raise RuntimeError(f"全部 {len(targets)} 个目标会话推送失败")

    @filter.command_group("bug_report")
    def bug_report(self) -> None:
        """禅道日报命令组。"""

    @bug_report.command("health")
    async def health(self, event: AstrMessageEvent) -> None:
        """检查 Huly Bridge 配置状态（不回显敏感信息）。"""
        client = self._client()
        push = "已开启" if self.config.get("push_enabled") else "关闭"
        targets = self._push_targets()
        yield event.plain_result(
            f"Huly 日报健康检查\n"
            f"凭据：{self._auth_summary(client)}\n"
            f"Bridge 地址：{'已配置' if self.config.get('huly_bridge_url') else '未配置'}\n"
            f"推送：{push}\n"
            f"推送目标：{len(targets)} 个会话（轮询间隔 {self._push_interval():g} 秒）"
        )

    @bug_report.command("status")
    async def status(self, event: AstrMessageEvent) -> None:
        """查看插件配置与推送开关状态。"""
        project_ids = parse_ids(str(self.config.get("scope_project_ids", "")))
        targets = self._push_targets()
        yield event.plain_result(
            f"Huly 日报状态\n"
            f"标题：{self.config.get('report_title', 'Huly 每日缺陷日报')}\n"
            f"项目范围：{sorted(project_ids) or '全部'}\n"
            f"风格：{self._style()}\n"
            f"推送：{'开启' if self.config.get('push_enabled') else '关闭'}\n"
            f"推送目标（{len(targets)} 个）：\n" + ("\n".join(f"  {i + 1}. {t}" for i, t in enumerate(targets)) or "  未配置")
        )

    @bug_report.command("styles")
    async def styles(self, event: AstrMessageEvent) -> None:
        """列出日报支持的渲染风格。"""
        yield event.plain_result("可用风格：" + "、".join(STYLES))

    @bug_report.command("preview")
    async def preview(self, event: AstrMessageEvent, style: str = "") -> None:
        """生成今日缺陷日报图片并预览。

        Args:
            style: 可选，指定渲染风格；留空使用配置中的默认风格。
        """
        try:
            _scopes, _bugs, report = await self._build_report_context()
            chosen = self._style(style)
            path = await self._to_thread_render(report, chosen)
            yield event.plain_result(f"风格：{chosen}")
            yield event.image_result(path)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Report preview failed")
            yield event.plain_result(f"日报预览失败：{exc}")

    async def _project_report(self, event: AstrMessageEvent, project: str = "") -> None:
        """Generate a read-only report for one project, for example ``/BR 509``.

        Args:
            project: ZenTao project ID or exact project name.
        """
        try:
            if not project.strip():
                parts = event.get_message_str().strip().split(maxsplit=1)
                project = parts[1] if len(parts) == 2 else ""
            report = await self._build_project_report_context(project)
            report["daily_comment"] = await self._ai_daily_comment(event, report)
            path = await self._to_thread_render(report, self._style())
            import astrbot.api.message_components as Comp

            event.stop_event()
            yield event.chain_result([
                Comp.Plain(f"{report['project_name']}缺陷日报已生成"),
                Comp.Image.fromFileSystem(path),
            ])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Project report preview failed")
            yield event.plain_result(f"项目日报生成失败：{exc}")
            event.stop_event()

    @filter.command("BG")
    async def project_report_bg(self, event: AstrMessageEvent, project: str = "") -> None:
        """Generate a project or product report with the ``/BG`` command."""
        async for result in self._project_report(event, project):
            yield result

    @filter.command("BR")
    async def project_report_br(self, event: AstrMessageEvent, project: str = "") -> None:
        """Generate a project or product report with the ``/BR`` command."""
        async for result in self._project_report(event, project):
            yield result

    @bug_report.command("summary")
    async def summary(self, event: AstrMessageEvent) -> None:
        """输出当前数据的规则化总结。"""
        try:
            _scopes, _bugs, report = await self._build_report_context()
            yield event.plain_result(build_rule_summary(report))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Summary failed")
            yield event.plain_result(f"总结生成失败：{exc}")

    @bug_report.command("review")
    async def review(self, event: AstrMessageEvent, scope: str = "", module: str = "") -> None:
        """查询项目/模块的待复核缺陷清单。

        Args:
            scope: 项目或产品 ID 或名称。
            module: 可选，模块 ID 或名称。
        """
        try:
            scopes, bugs_by_scope = await self._collect()
            result = build_review_items(scopes, bugs_by_scope, scope, module)
            if not result["items"]:
                yield event.plain_result("没有符合条件的待复核缺陷。")
                return
            lines = [f"{result['scope_label']} 待复核："]
            for item in result["items"]:
                lines.append(
                    f"#{item['id']} {item['title']}\n"
                    f"  指派人：{item['assignee']} · 状态：{item['status']} · {item['reason']}"
                )
            if result["truncated"]:
                lines.append("…以及更多（截断），请缩小模块范围。")
            yield event.plain_result("\n".join(lines))
        except Exception as exc:  # noqa: BLE001
            logger.exception("Review lookup failed")
            yield event.plain_result(f"待复核查询失败：{exc}")

    @bug_report.command("send")
    async def send(self, event: AstrMessageEvent, style: str = "") -> None:
        """立即生成并推送一份日报到所有目标群（需要推送开关和会话列表）。"""
        try:
            _scopes, _bugs, report = await self._build_report_context()
            await self._send_report(report, self._style(style))
            yield event.plain_result(f"日报已推送到 {len(self._push_targets())} 个目标会话。")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Send failed")
            yield event.plain_result(f"推送失败：{exc}")

    @bug_report.command("test")
    async def test(self, event: AstrMessageEvent, kind: str = "") -> None:
        """发送调试消息验证企业微信通道。

        Args:
            kind: ``text`` 发送文字，``image`` 发送图片，留空发送文字。
        """
        if kind.strip().lower() == "image":
            import astrbot.api.message_components as Comp

            chain = [Comp.Plain("日报图片测试："), Comp.Image.fromFileSystem("data/plugins/astrbot_plugin_zentao_report/test.png")]
            yield event.chain_result(chain)
            return
        yield event.plain_result("[测试] 日报文字通道正常。")

    async def terminate(self) -> None:
        """Release resources when the plugin is reloaded."""
        await super().terminate()
