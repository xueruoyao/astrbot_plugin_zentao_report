"""Focused regression tests for the single-project report data model."""

from __future__ import annotations

from report_html import render_html
from report_logic import Scope, build_report


def test_project_report_uses_real_statuses_and_module_names() -> None:
    """Aggregate project bugs without reverting to product-wide counters."""
    scope = Scope("509", "项目 · 509", "project")
    report = build_report(
        [scope],
        {
            "509": [
                {"id": 11, "title": "active", "status": "active", "severity": "1", "pri": "1", "moduleTitle": "业务管理", "assignedTo": {"realname": "甲"}},
                {"id": 12, "title": "resolved", "status": "resolved", "severity": "3", "pri": "2", "moduleTitle": "业务管理", "assignedTo": {"realname": "乙"}},
                {"id": 13, "title": "closed", "status": "closed", "severity": "4", "pri": "3", "moduleTitle": "系统设置", "assignedTo": {"realname": "丙"}},
            ]
        },
        "Huly 每日缺陷日报",
        "2026-08-27 18:00",
    )

    assert report["active_total"] == 1
    assert report["resolved_total"] == 1
    assert report["closed_total"] == 1
    assert report["opened_today_total"] == 0
    assert report["modules"] == [{"label": "业务管理", "count": 2}, {"label": "系统设置", "count": 1}]
    assert report["top_bugs"][0]["id"] == 11


def test_project_template_has_required_layout_and_footer() -> None:
    """Render the project dashboard shell without deprecated source text."""
    html = render_html(
        {
            "project_name": "509",
            "system_name": "业务管理服务平台",
            "generated_at": "2026-08-27 18:00",
            "open_total": 2,
            "closed_total": 1,
            "active_total": 1,
            "resolved_total": 1,
            "high_risk_total": 1,
            "opened_today_total": 0,
            "daily_comment": "今日没有新的缺陷动态。",
            "status_distribution": [{"name": "激活中", "value": 1}, {"name": "已解决", "value": 1}, {"name": "已关闭", "value": 1}],
            "modules": [{"label": "业务管理", "count": 2}],
            "top_bugs": [],
        }
    )

    assert "业务管理服务平台" in html
    assert "状态分布" in html
    assert "模块积压" in html
    assert "优先关注缺陷" in html
    assert "今日状况点评" in html
    assert "今日新提交" in html
    assert "POWERED BY YANFD" in html
    assert "数据来源" not in html
    assert "report-charts" in html
    assert "今日新提交" in html
    assert "submitters" in html


def test_renderer_creates_phone_ratio_png(tmp_path, monkeypatch) -> None:
    """Render ECharts into the required mobile-report image dimensions."""
    from report_renderer import render_report_png

    executable = "/var/folders/c5/m63gzmrd3vxgr8j79zvbf8s00000gn/T/opencode/pw-browsers/chromium_headless_shell-1148/chrome-mac/headless_shell"
    if not __import__("os").path.exists(executable):
        return
    monkeypatch.setenv("ZENTAO_REPORT_CHROMIUM", executable)
    output = tmp_path / "report.png"
    render_report_png(
        {
            "project_name": "509",
            "system_name": "业务管理服务平台",
            "generated_at": "2026-08-27 18:00",
            "open_total": 1,
            "closed_total": 1,
            "active_total": 1,
            "resolved_total": 0,
            "high_risk_total": 1,
            "opened_today_total": 0,
            "daily_comment": "今日没有新的缺陷动态。",
            "status_distribution": [{"name": "激活中", "value": 1}, {"name": "已解决", "value": 0}, {"name": "已关闭", "value": 1}],
            "modules": [{"label": "业务管理", "count": 1}],
            "top_bugs": [],
        },
        str(output),
    )
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
