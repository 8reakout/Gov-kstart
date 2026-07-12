from __future__ import annotations

import os
import smtplib
from pathlib import Path
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


def send_html_email(
    subject: str,
    html_body: str,
    attachment_path: Path | None = None,
) -> None:
    """HTML 이메일을 발송하고, 필요하면 HTML 파일을 첨부합니다."""

    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_use_tls = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    mail_from = os.getenv("MAIL_FROM", smtp_user)
    mail_to = os.getenv("MAIL_TO", "")
    mail_cc = os.getenv("MAIL_CC", "")

    if not smtp_host:
        raise ValueError("SMTP_HOST 값이 없습니다.")

    if not smtp_user:
        raise ValueError("SMTP_USER 값이 없습니다.")

    if not smtp_password:
        raise ValueError("SMTP_PASSWORD 값이 없습니다.")

    if not mail_to:
        raise ValueError("MAIL_TO 값이 없습니다.")

    to_recipients = [x.strip() for x in mail_to.split(",") if x.strip()]
    cc_recipients = [x.strip() for x in mail_cc.split(",") if x.strip()]
    all_recipients = to_recipients + cc_recipients

    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = mail_from
    msg["To"] = ", ".join(to_recipients)

    if cc_recipients:
        msg["Cc"] = ", ".join(cc_recipients)

    # 메일 본문 영역
    body_part = MIMEMultipart("alternative")

    text_body = (
        "K-Startup 공고 알림입니다.\n\n"
        "메일 본문이 정상적으로 보이지 않으면 첨부된 HTML 파일을 다운로드해서 확인하세요."
    )

    body_part.attach(MIMEText(text_body, "plain", "utf-8"))
    body_part.attach(MIMEText(html_body, "html", "utf-8"))

    msg.attach(body_part)

    # HTML 파일 첨부
    if attachment_path and attachment_path.exists():
        file_bytes = attachment_path.read_bytes()

        attachment = MIMEApplication(file_bytes, _subtype="html")
        attachment.add_header(
            "Content-Disposition",
            "attachment",
            filename=attachment_path.name,
        )

        msg.attach(attachment)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if smtp_use_tls:
            server.starttls()

        server.login(smtp_user, smtp_password)
        server.sendmail(mail_from, all_recipients, msg.as_string())