# TSK China Watch

每天监测 The Scholarly Kitchen（scholarlykitchen.sspnet.org）新发布的文章，
匹配标题或正文中的 "China" / "Chinese"，生成：

- **累计档案页**（GitHub Pages，永久访问链接）
- **每日更新邮件**（北京时间每天 07:00，发送到指定邮箱，仅当天有新命中才发）

---

## 部署步骤

### 1. 注册并验证 GitHub 账号

如果还没有，先完成注册和邮箱验证。

### 2. 新建一个公开仓库

例如仓库名 `tsk-china-watch`。把这个项目里的所有文件（包括 `.github/` 隐藏目录）
上传进去，保持目录结构不变：

```
tsk-china-watch/
├── .github/workflows/daily.yml
├── docs/index.html            ← GitHub Pages 发布这个文件
├── state/state.json           ← 处理状态（首次为空）
├── templates/
│   ├── dashboard_template.html
│   └── email_template.html
├── scraper.py
├── summarize.py
├── render.py
├── send_email.py
├── main.py
├── requirements.txt
└── README.md
```

### 3. 启用 GitHub Actions

仓库 Settings → Actions → General，确认 Actions 处于启用状态。

### 4. 启用 GitHub Pages

仓库 Settings → Pages → Source 选择 `Deploy from a branch`，
Branch 选择你上传代码的分支，目录选择 `/docs`。保存后，GitHub 会给出一个形如

```
https://<你的用户名>.github.io/tsk-china-watch/
```

的地址——**这就是永久访问链接**，每天手动打开即可看到最新累计结果。

### 5. Gmail 开启两步验证并生成应用专用密码

Google 账号 → 安全性 → 两步验证（先开启）→ 应用专用密码，
生成一个 16 位密码，专门给这个项目用。**不要用日常登录密码。**

### 6. 在 GitHub Secrets 中配置以下项

仓库 Settings → Secrets and variables → Actions → New repository secret：

| Secret 名称 | 说明 |
|---|---|
| `GMAIL_ADDRESS` | 发件 Gmail 地址 |
| `GMAIL_APP_PASSWORD` | 第 5 步生成的应用专用密码 |
| `MAIL_TO` | 收件地址，填 `hmao@wiley.com` |
| `DASHBOARD_URL` | 第 4 步拿到的 GitHub Pages 地址 |

中文摘要不需要额外配置——`.github/workflows/daily.yml` 里已经加了
`permissions: models: read`，GitHub Actions 运行时会自动提供
`GITHUB_TOKEN`，`summarize.py` 直接用它调用 GitHub 内置的免费推理服务
（GitHub Models，模型用的是 `openai/gpt-4o-mini`），不用注册任何新账号、
不用绑定信用卡。

### 7. 手动执行首次历史回溯并核对结果

仓库 Actions 标签页 → 选择 "Daily China Watch" 工作流 → **Run workflow**（手动触发）。

首次运行会回溯建站以来的全部文章（用时较长，请求做了限速，属正常现象），
只发一封统计邮件，不会把全部历史结果塞进邮件正文。运行完成后打开 GitHub Pages
链接，核对累计档案是否正确。

### 8. 确认每日定时任务生效

首次核对无误后不需要额外操作——`.github/workflows/daily.yml` 里已经配置了
北京时间每天 07:00（对应 UTC 前一天 23:00）自动运行。之后每天：

- 有新命中文章 → 更新 GitHub Pages 累计档案，并发送更新邮件到 `MAIL_TO`
- 没有新命中 → 只更新运行记录，不发邮件
- 抓取或渲染失败 → 不推进处理状态，且会发一封故障通知邮件（同一收件地址）

---

## 已知的限制和假设

- 需要根据实际网站结构核对一次 `robots.txt` 和使用条款（`scraper.py` 里访问的是
  WordPress REST API `/wp-json/wp/v2/posts` 和 RSS `/feed/`，两者通常都允许抓取，
  但部署前建议再次确认）。
- 中文摘要现在走 GitHub Models（GitHub 内置、免费，用 Actions 自动提供的
  `GITHUB_TOKEN` 调用），不需要额外账号或密钥。如果你所在的组织把
  Models 访问权限锁住了，找组织管理员在 Organization Settings → Policies
  （或 Copilot 相关设置）里放开即可；放不开的话，`summarize.py` 调用失败会
  自动留空，不影响其他功能。
- 如果你的公司另有部署的企业版 Copilot（比如走 Azure OpenAI 或者
  GitHub Copilot 的组织级订阅），也可以把 `summarize.py` 换成调用那个
  端点，思路一样：把摘录发过去、要求一句话转述大意，替换掉里面的
  `requests.post(...)` 目标地址和鉴权方式即可。
- 邮件发送逻辑遵循"当天没有新命中就不发邮件"的规则。如果你想改成
  "无论是否有新命中，每天 07:00 都发一封（哪怕内容是'今日无更新'）"，
  只需要在 `main.py` 里把 `if new_hits:` 判断去掉即可，模板已经支持空状态
  （见 `email_template.html` 里的"今日没有新的中国相关命中文章"分支）。
