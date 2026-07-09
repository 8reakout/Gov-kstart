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
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return set()


def save_seen_ids(path: Path, ids: set[str]) -> None:
    path.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def build_message(notices: list[Notice], seen_ids: set[str]) -> tuple[str, str, list[Notice]]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    new_notices = [n for n in notices if n.notice_id not in seen_ids]

    title = f"K-Startup 모집중 공고 신규 {len(new_notices)}건 / 전체 {len(notices)}건"

    lines = [
        "[K-Startup 모집중 공고]",
        f"조회시각: {now}",
        f"신규: {len(new_notices)}건 / 전체: {len(notices)}건",
        "",
    ]

    if not notices:
        lines.append("현재 조건에 맞는 모집중 공고가 없습니다.")
        return title, "\n".join(lines), new_notices

    for idx, notice in enumerate(notices, 1):
        mark = "신규" if notice.notice_id not in seen_ids else "기존"
        period = " ~ ".join(x for x in [notice.start_date, notice.end_date] if x) or "페이지 확인 필요"
        lines.extend(
            [
                f"{idx}. [{mark}] {notice.title}",
                f"- 분류: {notice.category or '-'}",
                f"- 기관: {notice.organization or '-'}",
                f"- 상태: {notice.status or '모집중 조건 조회'}",
                f"- 접수기간/마감: {period}",
                f"- 링크: {notice.url or '-'}",
                "",
            ]
        )

    return title, "\n".join(lines), new_notices


def run() -> None:
    config = load_config()
    state_config = config.get("state", {})
    seen_path = BASE_DIR / state_config.get("seen_file", "seen_notice_ids.json")
    latest_path = BASE_DIR / state_config.get("latest_file", "latest_notices.json")

    seen_ids = load_seen_ids(seen_path)
    notices = fetch_kstartup_notices(config)

    title, message, new_notices = build_message(notices, seen_ids)
    print(message)

    notification = config.get("notification", {})
    method = notification.get("method", "slack")
    if method != "slack":
        raise ValueError(f"현재 예제는 slack 알림만 지원합니다. method={method}")

    send_slack_message(notification.get("slack", {}), title, message)

    all_ids = seen_ids | {n.notice_id for n in notices}
    save_seen_ids(seen_path, all_ids)

    latest_path.write_text(
        json.dumps([n.to_dict() for n in new_notices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
