"""
main.py — 每日运行入口。GitHub Actions 定时触发这个脚本。

流程：
  1. 加载 state.json；若从未处理过任何文章，视为首次历史回溯。
  2. 抓取并匹配 China/Chinese，更新 state（未命中的文章也记录，避免重复检查）。
  3. 对当天新命中的文章调用 summarize.py 生成中文摘要，写回 state。
  4. 从 state 里取出全部命中过的文章，渲染累计档案页到 docs/index.html。
  5. 若当天有新命中：
       - 首次回溯：只发一封统计邮件（不塞入全部历史结果）。
       - 日常运行：发送当日更新邮件到 MAIL_TO。
     当天没有新命中：不发邮件，只更新运行状态。
  6. 记录 last_success_run；抓取或渲染异常时不推进这个时间戳，
     由 GitHub Actions 判定失败并发故障通知（见 workflow 文件）。

环境变量：
  DASHBOARD_URL   GitHub Pages 的完整访问地址，写进邮件里的"查看完整档案"链接
  MAIL_TO / GMAIL_ADDRESS / GMAIL_APP_PASSWORD  见 send_email.py
  GITHUB_TOKEN    GitHub Actions 自动提供，summarize.py 用它调用免费的
                  GitHub Models 生成中文摘要（不需要额外配置）
"""

import os
import sys
from datetime import datetime, timezone

from scraper import discover_new_articles, load_state, save_state
from render import render_dashboard, render_email
from send_email import send_daily_email

try:
    from summarize import summarize_hit
except Exception:
    # ANTHROPIC_API_KEY 未配置等情况下，摘要功能整体跳过，
    # 不影响抓取、匹配和累计档案的正常运行。
    summarize_hit = None


def build_all_matched_entries(state):
    """从 state 里重建全部命中过的文章列表，按发布时间倒序，附带序号。"""
    matched = [
        {"url": url, **data}
        for url, data in state["processed"].items()
        if data.get("matched")
    ]
    matched.sort(key=lambda e: e["published"], reverse=True)
    for i, entry in enumerate(matched):
        entry["index"] = len(matched) - i
    return matched


def since_date_from(state):
    dates = [
        data["published"][:10]
        for data in state["processed"].values()
        if data.get("matched")
    ]
    return min(dates) if dates else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    state = load_state()
    is_first_run = len(state["processed"]) == 0

    try:
        new_hits = discover_new_articles(state, backfill=is_first_run)
    except Exception as exc:
        print(f"抓取失败，不推进成功水位：{exc}", file=sys.stderr)
        sys.exit(1)  # GitHub Actions 标记本次运行失败，触发故障通知

    # 对当天新命中的文章生成中文摘要
    for hit in new_hits:
        summary = ""
        if summarize_hit is not None:
            summary = summarize_hit(hit["excerpt_html"])
        hit["summary"] = summary
        state["processed"][hit["url"]]["summary"] = summary

    save_state(state)

    all_matched = build_all_matched_entries(state)
    since_date = since_date_from(state)

    render_dashboard(all_matched, new_today_count=len(new_hits), since_date=since_date)

    if new_hits:
        dashboard_url = os.environ.get("DASHBOARD_URL", "")
        if is_first_run:
            # 首次回溯：只发统计邮件和档案链接，不把全部历史结果塞进邮件正文
            subject = f"[TSK China Watch] 首次历史回溯完成：共 {len(new_hits)} 篇命中文章"
            html_body = (
                f"<p>历史回溯已完成，共发现 {len(new_hits)} 篇提到 China/Chinese 的文章。</p>"
                f'<p><a href="{dashboard_url}">查看完整累计档案 →</a></p>'
            )
        else:
            # 按发布时间倒序排列当天新命中的文章，再传给邮件模板
            today_entries = sorted(
                new_hits, key=lambda e: e["published"], reverse=True
            )
            for i, entry in enumerate(today_entries):
                entry["index"] = len(today_entries) - i
            subject, html_body = render_email(
                today_entries,
                total_count=len(all_matched),
                since_date=since_date,
                dashboard_url=dashboard_url,
            )
        send_daily_email(subject, html_body)
    else:
        print("今日没有新命中文章，不发邮件，仅更新运行状态。")

    state["last_success_run"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == "__main__":
    main()
