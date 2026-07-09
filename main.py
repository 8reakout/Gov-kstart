from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from kstartup_fetch import Notice, fetch_kstartup_notices
from notifier import send_slack_message

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.yaml"


def load_config() -> dict[str, Any]:
    """config.yaml이 있으면 config.yaml을 사용하고, 없으면 config.example.yaml을 사용합니다."""
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen_ids(path: Path) -> set[str]:
    """이미 알림으로 보낸 공고 ID 목록을 읽습니다."""
    if not path.exists():
        return set()

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return set(str(x) for x in data)
        return set()
    except json.JSONDecodeError:
        return set()


def save_seen_ids(path: Path, ids: set[str]) -> None:
    """이번 실행에서 확인한 공고 ID까지 포함해서 저장합니다."""
    path.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def format_notice(notice: Notice, index: int) -> list[str]:
    """Slack 메시지에 표시할 공고 1건을 문자열 목록으로 만듭니다."""
    period = " ~ ".join(
        x for x in [notice.start_date, notice.end_date] if x
    ) or "페이지 확인 필요"

    return [
        f"{index}. {notice.title}",
        f"- 분류: {notice.category or '-'}",
        f"- 기관: {notice.organization or '-'}",
        f"- 상태: {notice.status or '모집중'}",
        f"- 접수기간/마감: {period}",
        f"- 링크: {notice.url or '-'}",
        "",
    ]


def build_message(
    notices: list[Notice],
    seen_ids: set[str],
) -> tuple[str, str, list[Notice], list[Notice]]:
    """전체 공고를 신규/기존으로 나누고 Slack 메시지를 생성합니다."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_notices = [n for n in notices if n.notice_id not in seen_ids]
    old_notices = [n for n in notices if n.notice_id in seen_ids]

    title = (
        f"K-Startup 모집중 공고 "
        f"신규 {len(new_notices)}건 / 기존 {len(old_notices)}건 / 전체 {len(notices)}건"
    )

    lines = [
        "[K-Startup 모집중 공고 알림]",
        f"조회시각: {now}",
        f"신규: {len(new_notices)}건 / 기존: {len(old_notices)}건 / 전체: {len(notices)}건",
        "",
    ]

    if not notices:
        lines.append("현재 조건에 맞는 모집중 공고가 없습니다.")
        return title, "\n".join(lines), new_notices, old_notices

    lines.append("🆕 [신규 공고]")
    if new_notices:
        for idx, notice in enumerate(new_notices, 1):
            lines.extend(format_notice(notice, idx))
    else:
        lines.append("이번 실행에서 새로 확인된 공고는 없습니다.")
        lines.append("")

    lines.append("📌 [기존 공고]")
    if old_notices:
        for idx, notice in enumerate(old_notices, 1):
            lines.extend(format_notice(notice, idx))
    else:
        lines.append("아직 기존 공고가 없습니다.")
        lines.append("")

    return title, "\n".join(lines), new_notices, old_notices


def run() -> None:
    config = load_config()

    state_config = config.get("state", {})
    seen_path = BASE_DIR / state_config.get("seen_file", "seen_notice_ids.json")
    latest_path = BASE_DIR / state_config.get("latest_file", "latest_notices.json")

    seen_ids = load_seen_ids(seen_path)

    notices = fetch_kstartup_notices(config)

    title, message, new_notices, old_notices = build_message(notices, seen_ids)

    print(message)

    notification = config.get("notification", {})
    method = notification.get("method", "slack")

    if method != "slack":
        raise ValueError(f"현재 예제는 slack 알림만 지원합니다. method={method}")

    send_slack_message(
        notification.get("slack", {}),
        title,
        message,
    )

    # 이번에 조회된 모든 공고 ID를 저장합니다.
    # 다음 실행부터는 같은 notice_id가 기존 공고로 분류됩니다.
    all_ids = seen_ids | {n.notice_id for n in notices}
    save_seen_ids(seen_path, all_ids)

    # latest_notices.json에는 신규 공고만 저장합니다.
    # GitHub에 커밋할 필요는 없고, Actions artifact 확인용으로만 사용하면 됩니다.
    latest_path.write_text(
        json.dumps([n.to_dict() for n in new_notices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
