"""Pure aggregation logic for ZenTao reports."""

import re
from datetime import date, datetime
from zoneinfo import ZoneInfo


class Scope:
    """Describe a report scope.

    Args:
        id: Project scope identifier (string, e.g. a Huly project identifier).
        name: Display name for the scope.
        kind: Scope category.
    """

    def __init__(self, id: str, name: str, kind: str) -> None:
        self.id = id
        self.name = name
        self.kind = kind


def parse_ids(value: str) -> set[str]:
    """Parse a comma-separated string of project identifiers.

    Args:
        value: Comma-separated identifier text.

    Returns:
        A set containing all non-empty trimmed identifiers.
    """

    return {item.strip() for item in value.split(",") if item.strip()}


def _person_name(value: object) -> str:
    """Return a display name from a ZenTao person value."""

    if isinstance(value, dict):
        name = value.get("realname") or value.get("account")
    else:
        name = value
    return str(name).strip() if name is not None and str(name).strip() else "未分配"


def build_review_items(
    scopes: list[Scope],
    bugs_by_scope: dict[str, list[dict]],
    scope_filter: str = "",
    module_filter: str = "",
    limit: int = 20,
) -> dict:
    """Build a pending-review list for one scope, optionally filtered by module.

    A bug is pending review when it is resolved, or was reopened after a
    resolution. The reopened rule is approximated from the ``actions`` list
    when present; otherwise resolved status alone is used.

    Args:
        scopes: Report scopes (products and projects).
        bugs_by_scope: Bugs grouped by scope ID.
        scope_filter: A scope ID or exact scope name.
        module_filter: A module ID or exact module name.
        limit: Maximum number of items to return.

    Returns:
        A dictionary with ``items`` and a ``truncated`` flag.
    """
    matched_scope: Scope | None = None
    for scope in scopes:
        if scope_filter and scope_filter not in {str(scope.id), scope.name}:
            continue
        matched_scope = scope
        break

    if matched_scope is None:
        return {"items": [], "truncated": False, "scope_label": scope_filter or ""}

    items = []
    for bug in bugs_by_scope.get(matched_scope.id, []):
        label = str(bug.get("moduleTitle") or bug.get("moduleName") or "").strip()
        if module_filter and module_filter not in {str(bug.get("module", "")), label}:
            continue

        status = _status(bug.get("status"))
        actions = bug.get("actions") or []
        reopened = any(
            re.search(r"reopen|re-open|重新打开|激活|reopened", str(a.get("action", "")))
            for a in actions
            if isinstance(a, dict)
        )
        reason = "重新打开待复核" if reopened else "待验证"
        if status in {"resolved", "已解决"} or reopened:
            items.append(
                {
                    "id": _number(bug.get("id")),
                    "title": str(bug.get("title") or "未命名缺陷"),
                    "assignee": _person_name(bug.get("assignedTo")),
                    "status": str(bug.get("status") or ""),
                    "resolved_date": str(bug.get("resolvedDate") or ""),
                    "reason": reason,
                }
            )

    items.sort(key=lambda item: (-_number(item["id"])))
    return {
        "items": items[:limit],
        "truncated": len(items) > limit,
        "scope_label": matched_scope.name,
    }


def build_rule_summary(report: dict) -> str:
    """Build a deterministic rule-based summary from the report context.

    Unlike an LLM summary, this never invents assignees or statuses: it quotes
    only computed totals and the top ranked rows.

    Args:
        report: Aggregated report context from ``build_report``.

    Returns:
        A short Chinese summary string.
    """
    top_module = report["modules"][0]["label"] if report["modules"] else "暂无"
    top_submitter = report["submitters"][0] if report["submitters"] else None
    lines = [
        f"未关闭 {report['open_total']} 项，已关闭 {report['closed_total']} 项，"
        f"高风险 S1/S2 共 {report['high_risk_total']} 项。",
        f"缺陷最集中的模块是「{top_module}」。",
    ]
    if top_submitter:
        lines.append(
            f"今日新建最多为 {top_submitter['name']}，共 {top_submitter['count']} 条。"
        )
    lines.append("（以上由规则生成，未使用大模型。）")
    return "".join(lines)


def build_snapshot(report: dict, generated_at: str) -> dict:
    """Extract a compact trend snapshot from a report context.

    Snapshot values are persisted for a longer history so the recorded facts
    never depend on the report image layout.

    Args:
        report: Aggregated report context.
        generated_at: ISO timestamp for the snapshot.

    Returns:
        A small dictionary with totals only.
    """
    return {
        "generated_at": generated_at,
        "open": report["open_total"],
        "closed": report["closed_total"],
        "active": report["active_total"],
        "high": report["high_risk_total"],
    }


def _status(value: object) -> str:
    """Normalize a status value for comparisons."""

    return str(value or "").strip().lower()


def _number(value: object, default: int = 0) -> int:
    """Convert a value to an integer without failing aggregation."""

    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _opened_today(value: object) -> bool:
    """Check whether a ZenTao date value belongs to today."""

    if not value:
        return False
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text) == datetime.now(ZoneInfo("Asia/Shanghai")).date()
    except ValueError:
        return False


def build_report(
    scopes: list[Scope],
    bugs_by_scope: dict[str, list[dict]],
    title: str,
    generated_at: str,
    top_bug_limit: int = 5,
) -> dict:
    """Aggregate ZenTao bugs into a renderer-friendly report context.

    Args:
        scopes: Configured product or project scopes.
        bugs_by_scope: Bugs grouped by their scope identifier.
        title: Report title.
        generated_at: Report generation timestamp for display.
        top_bug_limit: Maximum number of defects shown in the attention list.

    Returns:
        A dictionary containing report metrics and ranked lists.
    """

    scope_names = {scope.id: scope.name for scope in scopes}
    scope_rows = []
    module_counts: dict[str, int] = {}
    submitter_counts: dict[str, int] = {}
    attention_candidates = []
    top_bugs = []
    open_total = closed_total = active_total = resolved_total = high_risk_total = 0
    opened_today_total = resolved_today_total = 0
    resolved_today_by_person: dict[str, int] = {}

    for scope in scopes:
        open_count = closed_count = high_count = 0
        for bug in bugs_by_scope.get(scope.id, []):
            status = _status(bug.get("status"))
            is_closed = status in {"closed", "已关闭"}
            severity = _number(bug.get("severity"))
            bug_id = _number(bug.get("id"))

            if is_closed:
                closed_total += 1
                closed_count += 1
            else:
                open_total += 1
                open_count += 1
                if severity <= 2:
                    high_risk_total += 1
                    high_count += 1
                    attention_candidates.append(
                        (
                            severity,
                            _number(bug.get("pri")),
                            -bug_id,
                            {
                                "id": bug_id,
                                "title": str(bug.get("title") or ""),
                                "scope": str(scope.name),
                                "assignee": _person_name(bug.get("assignedTo")),
                                "status": str(bug.get("status") or ""),
                                "severity": severity,
                            },
                        )
                    )
            module = bug.get("moduleTitle") or bug.get("moduleName") or "未设置模块"
            module_label = str(module).strip() or "未设置模块"
            module_counts[module_label] = module_counts.get(module_label, 0) + 1

            if status in {"active", "激活"}:
                active_total += 1
            if status in {"resolved", "已解决"}:
                resolved_total += 1

            if _opened_today(bug.get("openedDate")):
                opened_today_total += 1
                submitter = _person_name(bug.get("openedBy"))
                submitter_counts[submitter] = submitter_counts.get(submitter, 0) + 1
            if _opened_today(bug.get("resolvedDate")):
                resolved_today_total += 1
                resolver = _person_name(bug.get("resolvedBy"))
                resolved_today_by_person[resolver] = resolved_today_by_person.get(resolver, 0) + 1

            top_bugs.append(
                {
                    "id": bug_id,
                    "title": str(bug.get("title") or "未命名缺陷"),
                    "status": str(bug.get("status") or "未知"),
                    "severity": severity,
                    "priority": _number(bug.get("pri")),
                    "assignee": _person_name(bug.get("assignedTo")),
                    "module": str(bug.get("moduleTitle") or bug.get("moduleName") or "未设置模块").strip() or "未设置模块",
                }
            )

        scope_rows.append(
            {
                "label": str(scope.name),
                "open": open_count,
                "closed": closed_count,
                "high": high_count,
            }
        )

    scope_rows.sort(key=lambda item: (-item["open"], -item["high"]))
    modules = [
        {"label": label, "count": count}
        for label, count in sorted(module_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
    ]
    submitters = [
        {"name": name, "count": count}
        for name, count in sorted(submitter_counts.items(), key=lambda item: (-item[1], item[0]))[:8]
        if count > 0
    ]
    attention_candidates.sort(key=lambda item: item[:3])
    top_bugs.sort(key=lambda item: (item["status"] in {"closed", "已关闭"}, item["severity"] or 99, item["priority"] or 99, -item["id"]))
    top_resolver = max(resolved_today_by_person.items(), key=lambda item: (item[1], item[0]), default=None)
    if top_resolver:
        daily_comment = f"{top_resolver[0]} 今日解决 {top_resolver[1]} 个缺陷，值得点赞。"
    elif resolved_today_total:
        daily_comment = f"今日已解决 {resolved_today_total} 个缺陷，修复工作持续推进。"
    elif opened_today_total:
        daily_comment = f"今日新增 {opened_today_total} 个缺陷，优先关注高风险与激活中的积压。"
    else:
        daily_comment = "今日没有新的缺陷动态，建议继续跟进激活中和待验证的积压。"
    if open_total:
        daily_comment += f" 仍有 {open_total} 个未关闭缺陷待处理。"

    # Keep the lookup explicit so the fallback remains correct for malformed data.
    for item in attention_candidates:
        bug_id = item[3]["id"]
        item[3]["scope"] = item[3]["scope"] or scope_names.get(bug_id, f"范围#{bug_id}")

    return {
        "title": title,
        "generated_at": generated_at,
        "open_total": open_total,
        "closed_total": closed_total,
        "active_total": active_total,
        "resolved_total": resolved_total,
        "high_risk_total": high_risk_total,
        "opened_today_total": opened_today_total,
        "resolved_today_total": resolved_today_total,
        "daily_comment": daily_comment,
        "status_distribution": [
            {"name": "激活中", "value": active_total},
            {"name": "已解决", "value": resolved_total},
            {"name": "已关闭", "value": closed_total},
            {
                "name": "其他状态",
                "value": max(0, open_total + closed_total - active_total - resolved_total - closed_total),
            },
        ],
        "scope_count": len(scopes),
        "scopes": scope_rows,
        "modules": modules,
        "submitters": submitters,
        "attention": [item[3] for item in attention_candidates[:6]],
        "top_bugs": top_bugs[:max(1, top_bug_limit)],
    }
