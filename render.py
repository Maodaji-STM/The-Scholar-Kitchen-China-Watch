"""
render.py — 把 state.json 里的处理结果渲染成：
  1. 累计档案页（docs/index.html，发布到 GitHub Pages）
  2. 当日邮件正文（仅当天新增命中时才需要）

两者共用同一份条目数据结构，按 templates/dashboard_template.html 和
templates/email_template.html 的字段要求组装。
"""

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path("templates")
DOCS_OUTPUT = Path("docs/index.html")

env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))


def _group_by_day(entries):
    """entries 已按 published 倒序排列；这里按日期分组，保持组间倒序。"""
    days = []
    current_date = None
    current_group = None
    for entry in entries:
        date_str = entry["published"][:10]  # ISO 日期部分 YYYY-MM-DD
        if date_str != current_date:
            current_group = {"date": date_str, "entries": []}
            days.append(current_group)
            current_date = date_str
        current_group["entries"].append(entry)
    return days


def render_dashboard(all_matched_entries, new_today_count, since_date):
    """
    all_matched_entries: 全部命中过的条目（按 published 倒序），每条包含
        index / author / matched_term / title / url / excerpt_html / summary
    """
    days = _group_by_day(all_matched_entries)
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")

    template = env.get_template("dashboard_template.html")
    html = template.render(
        days=days,
        last_run=now,
        new_today=new_today_count,
        total_count=len(all_matched_entries),
        since_date=since_date,
        generated_at=now,
    )

    DOCS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    DOCS_OUTPUT.write_text(html, encoding="utf-8")
    return DOCS_OUTPUT


def render_email(today_entries, total_count, since_date, dashboard_url):
    """
    today_entries: 当天新命中的条目（含 summary 字段）。
    返回 (subject, html_body)。调用方决定是否真的发送。
    """
    report_date = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d")
    subject = f"[TSK China Watch] {report_date}：{len(today_entries)} 篇新文章"

    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    template = env.get_template("email_template.html")
    html = template.render(
        email_subject=subject,
        report_date=report_date,
        entries=today_entries,
        new_count=len(today_entries),
        total_count=total_count,
        since_date=since_date,
        dashboard_url=dashboard_url,
        generated_at=now,
    )
    return subject, html
