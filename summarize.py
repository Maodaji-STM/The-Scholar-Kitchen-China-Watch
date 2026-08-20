"""
为每条命中结果生成中文摘要 —— 使用 GitHub Models（GitHub 内置的免费推理服务）。

不需要注册任何新账号、不需要绑定信用卡、不需要额外的 Secret：
GitHub Actions 运行时会自动提供 GITHUB_TOKEN，只要 workflow 里声明了
`permissions: models: read`（daily.yml 里已经配好），这个脚本就能直接用。

设计原则：
- 只把"已经提取好的短摘录"（关键词前后一两句话）发给模型，不把整篇原文发过去。
- 要求模型"转述大意"而不是"翻译原文"，摘要是一句话中文说明，
  不逐句对应英文措辞。
- 若调用失败（比如组织管理员限制了 Models 访问权限），摘要留空，
  不阻塞当天的抓取流程；该条目下次运行再补。

如果公司的 GitHub 组织把 Models 访问权限锁住了，找组织管理员在
Organization Settings → Policies（或 Copilot 相关设置）里放开即可，
不用改这份代码。
"""

import os
import re

import requests

ENDPOINT = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4o-mini"

SUMMARY_PROMPT = """以下是英文学术出版行业博客 The Scholarly Kitchen 中一篇文章里，
提到"China"或"Chinese"的原文片段（已经过滤掉与中国无关的内容）：

---
{excerpt}
---

请用一句中文（不超过 40 字）说明：这段内容具体在讨论中国的什么事情
（例如：某项政策、某个机构的动作、某种趋势、某个争议点等）。
只转述大意，不要逐句直译，不要添加原文没有的信息或评价。
只输出这一句话，不要任何前缀或解释。"""


def summarize_hit(excerpt_html: str) -> str:
    """excerpt_html: scraper.py 生成的带 <mark> 标签的英文摘录"""
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        # 本地手动运行、没有 Actions 环境时不会有这个 token，直接跳过摘要
        return ""

    excerpt_plain = re.sub(r"</?mark>", "", excerpt_html)
    try:
        resp = requests.post(
            ENDPOINT,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "model": MODEL,
                "messages": [
                    {
                        "role": "user",
                        "content": SUMMARY_PROMPT.format(excerpt=excerpt_plain),
                    }
                ],
                "max_tokens": 120,
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"].strip()
    except Exception:
        # 失败时留空，不中断当天流程。摘要字段为空的条目仍会正常
        # 出现在当日结果里，只是没有"摘要"这一行内容。
        return ""


if __name__ == "__main__":
    sample = (
        "...lays out the strategic choices facing international publishers as "
        "<mark>China's</mark> domestic journal infrastructure continues to mature and "
        "compete for submissions..."
    )
    print(summarize_hit(sample))
