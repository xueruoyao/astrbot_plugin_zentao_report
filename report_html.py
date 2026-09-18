"""Phone-ratio Jinja2 templates rendered by Playwright and ECharts."""

from __future__ import annotations

from typing import Any

from jinja2 import Template

CANVAS_WIDTH = 1080
STYLES = ("brutalism", "shadcn", "oneui", "skeuo", "graphite")

_THEMES = {
    "brutalism": {"bg": "#f4f0e6", "card": "#ffffff", "text": "#0a0a0a", "muted": "#4a4a4a", "line": "#0a0a0a", "accent": "#ff3b00", "active": "#0a3cff", "resolved": "#ffd400", "closed": "#6b7280", "radius": "0px", "shadow": "8px 8px 0 #0a0a0a"},
    "shadcn": {"bg": "#09090b", "card": "#151518", "text": "#fafafa", "muted": "#a1a1aa", "line": "#303036", "accent": "#818cf8", "active": "#f59e0b", "resolved": "#34d399", "closed": "#71717a", "radius": "12px", "shadow": "none"},
    "oneui": {"bg": "#f4f8fc", "card": "#ffffff", "text": "#0f172a", "muted": "#64748b", "line": "#e2e8f0", "accent": "#0a7dff", "active": "#ff7a1a", "resolved": "#00a8a8", "closed": "#94a3b8", "radius": "26px", "shadow": "0 8px 28px rgba(5,44,101,.08)"},
    "skeuo": {"bg": "#e5dece", "card": "#f4f0e4", "text": "#2c2a24", "muted": "#6b6455", "line": "#c8bc9b", "accent": "#c98f1a", "active": "#b5382a", "resolved": "#3f7d5c", "closed": "#8f887a", "radius": "16px", "shadow": "inset 0 1px 0 #fff,0 8px 16px -6px #0005"},
    "graphite": {"bg": "#080d12", "card": "#121c24", "text": "#e8f1f4", "muted": "#9cafb8", "line": "#2c414d", "accent": "#72e1ff", "active": "#f2b35d", "resolved": "#79e0b3", "closed": "#667a86", "radius": "14px", "shadow": "0 18px 40px #0006"},
}

_BOOT_CHART_SCRIPT = """\
window.__mountReportCharts = function () {
  if (!window.echarts) return;
  var payload = JSON.parse(document.getElementById('report-charts').textContent);
  var pie = echarts.init(document.getElementById('status-chart'));
  window.__reportChartsReady = false;
  var rendered = 0;
  function done() { rendered += 1; if (rendered === 2) window.__reportChartsReady = true; }
  pie.on('finished', done);
  pie.setOption({ animation: false,
    tooltip: { trigger: 'item' },
    series: [{ type: 'pie', radius: ['48%', '72%'], center: ['50%', '48%'],
      avoidLabelOverlap: true, label: { color: payload.text, fontSize: 16, formatter: '{b} {c}' },
      labelLine: { length: 9, length2: 10, lineStyle: { color: payload.line } }, data: payload.status }]
  });
  var modules = echarts.init(document.getElementById('module-chart'));
  modules.on('finished', done);
  modules.setOption({ animation: false,
    grid: { left: 10, right: 48, top: 10, bottom: 8, containLabel: true },
    xAxis: { type: 'value', min: 0, max: payload.modules.max, interval: payload.modules.interval, minInterval: 1, axisLabel: { color: payload.muted }, splitLine: { lineStyle: { color: payload.line } } },
    yAxis: { type: 'category', inverse: true, data: payload.modules.labels, axisTick: { show: false }, axisLine: { show: false }, axisLabel: { color: payload.text, fontSize: 15, width: 180, overflow: 'truncate' } },
    series: [{ type: 'bar', data: payload.modules.values, barMaxWidth: 26, itemStyle: { color: payload.accent, borderRadius: [0, 6, 6, 0] }, label: { show: true, position: 'right', color: payload.text, fontSize: 15 } }]
  });
  pie.resize();
  modules.resize();
};
"""

_TEMPLATE = Template(
    """
<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
 *{box-sizing:border-box}body{width:1080px;min-height:1560px;margin:0;background:{{ theme.bg }};color:{{ theme.text }};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif}.page{padding:48px 52px 36px}.eyebrow{color:{{ theme.accent }};font-size:17px;font-weight:800;letter-spacing:.16em}.header{display:flex;justify-content:space-between;align-items:flex-start;margin:12px 0 26px}.brand{display:flex;gap:18px;align-items:center}.avatar{width:70px;height:70px;border-radius:18px;background:{{ theme.accent }};color:{{ theme.bg }};font-size:28px;font-weight:850;display:grid;place-items:center;overflow:hidden;flex:none}.avatar img{width:100%;height:100%;object-fit:cover}.system{font-size:24px;font-weight:700;color:{{ theme.muted }}}h1{font-size:52px;line-height:1.12;margin:8px 0 0;letter-spacing:-1.5px}.date{font-size:18px;color:{{ theme.muted }};text-align:right;line-height:1.6}.overview{display:grid;grid-template-columns:3fr 7fr;gap:22px}.card{background:{{ theme.card }};border:1px solid {{ theme.line }};border-radius:{{ theme.radius }};box-shadow:{{ theme.shadow }};padding:24px}.card-title{font-size:22px;font-weight:800;margin-bottom:14px}.status-card{min-height:408px}.chart{width:100%;height:315px}.module-card{min-height:408px;display:flex;flex-direction:column;justify-content:center}.module-card .card-title{align-self:stretch}.module-chart{height:340px}.total{display:flex;gap:14px;align-items:baseline;margin:4px 0 4px}.total strong{font-size:54px;color:{{ theme.accent }}}.total span{font-size:18px;color:{{ theme.muted }}}.legend{display:grid;grid-template-columns:1fr 1fr;gap:8px 14px;margin-top:-8px}.legend div{font-size:16px;color:{{ theme.muted }};white-space:nowrap}.dot{display:inline-block;width:10px;height:10px;border-radius:99px;margin-right:7px}.insight{display:grid;grid-template-columns:1fr 180px;gap:22px;margin-top:22px;align-items:center}.comment{font-size:21px;line-height:1.55;font-weight:650;margin:0}.caption{color:{{ theme.muted }};font-size:15px;margin:0 0 8px}.today-count{border-left:1px solid {{ theme.line }};padding-left:24px;text-align:center}.today-count strong{font-size:46px;color:{{ theme.accent }};line-height:1}.today-count span{display:block;font-size:16px;color:{{ theme.muted }};margin-top:8px}.submitters{display:flex;justify-content:center;gap:16px;flex-wrap:wrap;margin-top:14px}.submitter{display:flex;gap:7px;align-items:baseline;color:{{ theme.muted }};font-size:16px}.submitter b{color:{{ theme.text }};font-size:18px}.bugs{margin-top:22px;padding:0;overflow:hidden}.bugs-head{padding:22px 24px 12px;display:flex;justify-content:space-between;align-items:center}.bugs-head small{color:{{ theme.muted }};font-size:15px}.bug{display:grid;grid-template-columns:86px 1fr 128px;gap:14px;align-items:center;padding:15px 24px;border-top:1px solid {{ theme.line }};min-height:72px}.bug-id{font-weight:800;color:{{ theme.accent }};font-size:17px}.bug-title{font-size:18px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bug-meta{font-size:14px;color:{{ theme.muted }};margin-top:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.badge{text-align:center;padding:6px 8px;border:1px solid {{ theme.line }};border-radius:999px;font-size:14px;color:{{ theme.text }};white-space:nowrap}.empty{padding:38px 24px;color:{{ theme.muted }};text-align:center;border-top:1px solid {{ theme.line }};font-size:18px}.footer{text-align:center;color:{{ theme.muted }};font-size:16px;letter-spacing:.14em;margin-top:24px}.footer b{color:{{ theme.accent }}}
</style></head><body><main class="page">
<div class="eyebrow">HULY · PROJECT BUG REPORT</div><header class="header"><div class="brand"><div class="avatar">{% if project_avatar_url %}<img src="{{ project_avatar_url }}" alt="{{ project_name }}">{% else %}{{ project_name[:2] }}{% endif %}</div><div><div class="system">{{ system_name }}</div><h1>{{ project_name }} · 缺陷日报</h1></div></div><div class="date">{{ generated_at }}</div></header>
<section class="overview"><article class="card status-card"><div class="card-title">状态分布</div><div class="total"><strong>{{ total }}</strong><span>总缺陷</span></div><div id="status-chart" class="chart"></div><div class="legend"><div><i class="dot" style="background:{{ theme.active }}"></i>激活中 {{ active_total }}</div><div><i class="dot" style="background:{{ theme.resolved }}"></i>已解决 {{ resolved_total }}</div><div><i class="dot" style="background:{{ theme.closed }}"></i>已关闭 {{ closed_total }}</div><div><i class="dot" style="background:{{ theme.accent }}"></i>高风险 {{ high_risk_total }}</div></div></article><article class="card module-card"><div class="card-title">模块积压</div><div id="module-chart" class="module-chart"></div></article></section>
<section class="card insight"><div><p class="caption">今日状况点评</p><p class="comment">{{ daily_comment }}</p></div><div class="today-count"><p class="caption">今日新提交</p><strong>{{ opened_today_total }}</strong><span>个缺陷</span><div class="submitters">{% for submitter in submitters %}<div class="submitter"><b>{{ submitter.name }}</b><span>{{ submitter.count }} 个</span></div>{% else %}<div class="submitter">暂无今日提交记录</div>{% endfor %}</div></div></section>
<section class="card bugs"><div class="bugs-head"><div class="card-title">优先关注缺陷</div><small>按状态、严重程度、优先级排序</small></div>{% for bug in top_bugs %}<div class="bug"><div class="bug-id">#{{ bug.id }}</div><div><div class="bug-title">{{ bug.title }}</div><div class="bug-meta">{{ bug.module }} · 指派 {{ bug.assignee }} · S{{ bug.severity or '-' }} / P{{ bug.priority or '-' }}</div></div><div class="badge">{{ bug.status }}</div></div>{% else %}<div class="empty">当前项目没有可展示的缺陷</div>{% endfor %}</section>
<footer class="footer"><b>POWERED BY YANFD</b></footer></main><script type="application/json" id="report-charts">{{ chart_payload | tojson }}</script><script>{{ boot_script | safe }}</script></body></html>
"""
)


def render_html(report: dict[str, Any], style: str = "graphite") -> str:
    """Render a project report HTML document with ECharts placeholders.

    Args:
        report: Aggregated one-project report context.
        style: One of the supported style names.

    Returns:
        Complete HTML for the Playwright renderer.

    Raises:
        KeyError: If the style is unknown.
    """
    if style not in _THEMES:
        raise KeyError(f"Unknown style {style!r}; choose one of {STYLES}")
    theme = _THEMES[style]
    status_by_name = {item["name"]: item["value"] for item in report.get("status_distribution", [])}
    total = report.get("open_total", 0) + report.get("closed_total", 0)
    modules = report.get("modules", [])[:7]
    context = dict(report)
    context.update(
        theme=theme,
        total=total,
        system_name=report.get("system_name", "Huly"),
        project_name=report.get("project_name", "项目日报"),
        chart_payload={
            "text": theme["text"],
            "muted": theme["muted"],
            "line": theme["line"],
            "accent": theme["accent"],
            "status": [
                {"name": "激活中", "value": status_by_name.get("激活中", 0), "itemStyle": {"color": theme["active"]}},
                {"name": "已解决", "value": status_by_name.get("已解决", 0), "itemStyle": {"color": theme["resolved"]}},
                {"name": "已关闭", "value": status_by_name.get("已关闭", 0), "itemStyle": {"color": theme["closed"]}},
                {"name": "其他状态", "value": status_by_name.get("其他状态", 0), "itemStyle": {"color": theme["line"]}},
            ] if total else [{"name": "无数据", "value": 1, "itemStyle": {"color": theme["line"]}}],
            "modules": {
                "labels": [item["label"] for item in modules],
                "values": [item["count"] for item in modules],
                "max": max(5, ((max([item["count"] for item in modules] + [1]) + 4) // 5) * 5),
                "interval": max(1, ((max([item["count"] for item in modules] + [1]) + 4) // 5)),
            },
        },
        boot_script=_BOOT_CHART_SCRIPT,
    )
    return _TEMPLATE.render(**context)
