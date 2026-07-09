from __future__ import annotations

import os
from typing import Any

import requests


def send_slack_message(slack_config: dict[str, Any], title: str, message: str) -> None:
    """Slack Incoming Webhook으로 메시지를 발송합니다."""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL") or slack_config.get("webhook_url")

    if not webhook_url:
        raise ValueError("SLACK_WEBHOOK_URL 환경변수 또는 slack.webhook_url 값이 없습니다.")

    payload = {
        "username": slack_config.get("username", "K-Startup 공고봇"),
        "icon_emoji": slack_config.get("icon_emoji", ":mega:"),
        "text": f"*{title}*\n\n{message}",
    }

    response = requests.post(webhook_url, json=payload, timeout=15)
    if response.status_code != 200:
        raise RuntimeError(f"Slack 알림 발송 실패: {response.status_code} / {response.text}")
