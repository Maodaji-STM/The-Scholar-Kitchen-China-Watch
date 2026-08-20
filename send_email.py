"""
send_email.py — 通过 Gmail SMTP（587/STARTTLS）发送日报邮件。

需要的环境变量（部署时写入 GitHub Secrets，工作流里注入）：
  GMAIL_ADDRESS       发件 Gmail 地址
  GMAIL_APP_PASSWORD  Gmail 两步验证下生成的应用专用密码（不是登录密码）
  MAIL_TO             收件地址，例如 hmao@wiley.com

日常 Gmail 登录密码不应出现在代码或仓库任何地方。
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_daily_email(subject: str, html_body: str):
    gmail_address = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]
    mail_to = os.environ["MAIL_TO"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = mail_to
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, [mail_to], msg.as_string())
