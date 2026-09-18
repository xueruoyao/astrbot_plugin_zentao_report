"""Playwright + ECharts renderer for the phone-ratio report HTML.

ECharts is bundled locally under ``assets/`` and injected so the chart
rendering is fully deterministic regardless of network access.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

if __package__:
    from .report_html import CANVAS_WIDTH, STYLES, render_html
else:
    from report_html import CANVAS_WIDTH, STYLES, render_html

CANVAS_HEIGHT = 1560

_BASE_DIR = Path(__file__).resolve().parent
_ECHARTS_PATH = _BASE_DIR / "assets" / "echarts.min.js"

_EXECUTABLE_CANDIDATES = (
    "/AstrBot/data/playwright/chrome-linux/headless_shell",
    "/ms-playwright/headless_shell",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
)


def _resolve_executable() -> str:
    """Pick the first available Playwright Chromium binary.

    Returns:
        An existing executable path, or an empty string.
    """
    configured = os.environ.get("ZENTAO_REPORT_CHROMIUM", "").strip()
    for candidate in (configured, *_EXECUTABLE_CANDIDATES):
        if os.path.exists(candidate):
            return candidate
    return ""


def render_report_png(report: dict[str, Any], output_path: str, style: str = "graphite") -> str:
    """Render a report to PNG using Playwright Chromium (no network).

    Args:
        report: Aggregated report context from ``build_report``.
        output_path: Destination PNG path.
        style: One of the style keys in ``STYLES``.

    Returns:
        The output path written.

    Raises:
        RuntimeError: If no Chromium binary can be located.
    """
    from playwright.sync_api import sync_playwright

    executable = _resolve_executable()
    if not executable:
        raise RuntimeError("未找到 Playwright Chromium 可执行文件")

    if style not in STYLES:
        style = "graphite"

    html = render_html(report, style)
    echarts_src = ""
    if _ECHARTS_PATH.exists():
        echarts_src = _ECHARTS_PATH.read_text(encoding="utf-8")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=executable,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        page = browser.new_page(viewport={"width": CANVAS_WIDTH, "height": CANVAS_HEIGHT})
        if echarts_src:
            page.set_content(
                html,
                wait_until="domcontentloaded",
            )
            page.evaluate(
                "(src) => { const s = document.createElement('script'); s.id = '__echarts_bundle__'; s.textContent = src; document.head.appendChild(s); }",
                echarts_src,
            )
            page.evaluate("window.__mountReportCharts && window.__mountReportCharts()")
        else:
            page.set_content(html)
        page.wait_for_function("window.__reportChartsReady === true", timeout=10_000)
        page.wait_for_timeout(100)
        page.screenshot(path=output_path)
        browser.close()
    return output_path
