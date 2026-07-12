from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

from email_notifier import send_html_email
from kstartup_fetch import Notice, fetch_kstartup_notices

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.yaml"
HTML_OUTPUT_PATH = BASE_DIR / "kstartup_notice_latest.html"


def load_config() -> dict[str, Any]:
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_seen_ids(path: Path) -> set[str]:
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
    path.write_text(
        json.dumps(sorted(ids), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _period_text(notice: Notice) -> str:
    return " ~ ".join(x for x in [notice.start_date, notice.end_date] if x) or "-"


def build_text_message(new_notices: list[Notice], old_notices: list[Notice], total_count: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "[K-Startup 모집중 공고 알림]",
        f"조회시각: {now}",
        f"신규: {len(new_notices)}건 / 기존: {len(old_notices)}건 / 전체: {total_count}건",
        "",
    ]

    if new_notices:
        lines.append("[신규 공고]")
        for idx, notice in enumerate(new_notices, 1):
            lines.extend(
                [
                    f"{idx}. {notice.title}",
                    f"- 분류: {notice.category or '-'}",
                    f"- 기관: {notice.organization or '-'}",
                    f"- 상태: {notice.status or '-'}",
                    f"- 접수기간: {_period_text(notice)}",
                    f"- 링크: {notice.url or '-'}",
                    "",
                ]
            )
    else:
        lines.append("이번 실행에서 새로 확인된 공고는 없습니다.")

    return "\n".join(lines)


def build_html_message(new_notices: list[Notice], old_notices: list[Notice], total_count: int) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows: list[str] = []
    for idx, notice in enumerate(new_notices, 1):
        title = html.escape(notice.title or "-")
        category = html.escape(notice.category or "-")
        organization = html.escape(notice.organization or "-")
        status = html.escape(notice.status or "-")
        period = html.escape(_period_text(notice))
        url = html.escape(notice.url or "")

        link_html = f'<a href="{url}" target="_blank">바로가기</a>' if url else "-"

        rows.append(
            f"""
            <tr>
                <td style="padding:10px;border:1px solid #ddd;text-align:center;">{idx}</td>
                <td style="padding:10px;border:1px solid #ddd;font-weight:600;">{title}</td>
                <td style="padding:10px;border:1px solid #ddd;text-align:center;">{category}</td>
                <td style="padding:10px;border:1px solid #ddd;">{organization}</td>
                <td style="padding:10px;border:1px solid #ddd;text-align:center;">{status}</td>
                <td style="padding:10px;border:1px solid #ddd;text-align:center;white-space:nowrap;">{period}</td>
                <td style="padding:10px;border:1px solid #ddd;text-align:center;">{link_html}</td>
            </tr>
            """
        )

    if not rows:
        rows.append(
            """
            <tr>
                <td colspan="7" style="padding:16px;border:1px solid #ddd;text-align:center;">
                    이번 실행에서 새로 확인된 공고는 없습니다.
                </td>
            </tr>
            """
        )

    return f"""
    <!doctype html>
    <html lang="ko">
    <head>
        <meta charset="utf-8">
        <title>K-Startup 모집중 공고 알림</title>
    </head>
    <body style="margin:0;padding:24px;background-color:#f6f7f9;font-family:Arial,'Apple SD Gothic Neo','Malgun Gothic',sans-serif;color:#222;">
        <div style="max-width:1100px;margin:0 auto;background:#fff;border:1px solid #e5e7eb;border-radius:12px;overflow:hidden;">
            <div style="padding:24px;background:#243b53;color:#fff;">
                <h2 style="margin:0 0 8px 0;font-size:22px;">K-Startup 모집중 공고 알림</h2>
                <p style="margin:0;font-size:14px;opacity:.9;">조회시각: {html.escape(now)}</p>
            </div>

            <div style="padding:20px 24px;border-bottom:1px solid #e5e7eb;">
                <span style="display:inline-block;margin-right:8px;padding:8px 12px;background:#e8f5e9;border-radius:20px;font-weight:600;">신규 {len(new_notices)}건</span>
                <span style="display:inline-block;margin-right:8px;padding:8px 12px;background:#eef2ff;border-radius:20px;font-weight:600;">기존 {len(old_notices)}건</span>
                <span style="display:inline-block;padding:8px 12px;background:#f3f4f6;border-radius:20px;font-weight:600;">전체 {total_count}건</span>
                <p style="margin:14px 0 0 0;color:#555;font-size:14px;">
                    기존 공고는 이미 이전에 발송된 공고입니다. 이 메일에는 신규 공고만 상세 표시합니다.
                </p>
            </div>

            <div style="padding:24px;">
                <h3 style="margin:0 0 12px 0;font-size:18px;">신규 공고 목록</h3>
                <table style="width:100%;border-collapse:collapse;font-size:14px;">
                    <thead>
                        <tr style="background:#f3f4f6;">
                            <th style="padding:10px;border:1px solid #ddd;">번호</th>
                            <th style="padding:10px;border:1px solid #ddd;">공고명</th>
                            <th style="padding:10px;border:1px solid #ddd;">분류</th>
                            <th style="padding:10px;border:1px solid #ddd;">기관</th>
                            <th style="padding:10px;border:1px solid #ddd;">상태</th>
                            <th style="padding:10px;border:1px solid #ddd;">접수기간</th>
                            <th style="padding:10px;border:1px solid #ddd;">링크</th>
                        </tr>
                    </thead>
                    <tbody>
                        {''.join(rows)}
                    </tbody>
                </table>
            </div>
        </div>
    </body>
    </html>
    """

def save_html_file(html_body: str) -> Path:
    """생성된 HTML 이메일 본문을 파일로 저장하고 파일 경로를 반환합니다."""
    HTML_OUTPUT_PATH.write_text(html_body, encoding="utf-8")
    print(f"[정보] HTML 파일 저장 완료: {HTML_OUTPUT_PATH}")
    return HTML_OUTPUT_PATH


def run() -> None:
    config = load_config()

    state_config = config.get("state", {})
    seen_path = BASE_DIR / state_config.get("seen_file", "seen_notice_ids.json")
    latest_path = BASE_DIR / state_config.get("latest_file", "latest_notices.json")

    seen_ids = load_seen_ids(seen_path)
    notices = fetch_kstartup_notices(config)

    new_notices = [n for n in notices if n.notice_id not in seen_ids]
    old_notices = [n for n in notices if n.notice_id in seen_ids]

    subject = f"[K-Startup] 신규 공고 {len(new_notices)}건 / 전체 {len(notices)}건"
    html_body = build_html_message(new_notices, old_notices, len(notices))
   
    html_file_path = save_html_file(html_body)

    send_html_email(
    subject=subject,
    html_body=html_body,
    attachment_path=html_file_path,
    )
    
    all_ids = seen_ids | {n.notice_id for n in notices}
    save_seen_ids(seen_path, all_ids)

    latest_path.write_text(
        json.dumps([n.to_dict() for n in new_notices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
