import os
import requests


def send_slack_message(slack_config: dict, title: str, message: str) -> None:
    webhook_url = (
        os.getenv("SLACK_WEBHOOK_URL")
        or slack_config.get("webhook_url")
    )

    if not webhook_url:
        raise ValueError(
            "SLACK_WEBHOOK_URL 환경변수 또는 slack.webhook_url 값이 없습니다."
        )

    username = slack_config.get("username", "사업공고 모니터링봇")
    icon_emoji = slack_config.get("icon_emoji", ":mag:")

    payload = {
        "username": username,
        "icon_emoji": icon_emoji,
        "text": f"*{title}*\n\n{message}",
    }

    response = requests.post(
        webhook_url,
        json=payload,
        timeout=10,
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"Slack 알림 발송 실패: {response.status_code} / {response.text}"
        )