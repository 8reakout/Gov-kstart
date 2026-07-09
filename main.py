from __future__ import annotations

import json
import os
import re
import smtplib
from dataclasses import dataclass, asdict
from datetime import datetime
from difflib import SequenceMatcher
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from notifier import send_slack_message
from dotenv import load_dotenv

import requests
import yaml
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

CONFIG_PATH = BASE_DIR / "config.yaml"
EXAMPLE_CONFIG_PATH = BASE_DIR / "config.example.yaml"
SEEN_PATH = BASE_DIR / "seen_urls.json"


@dataclass
class Notice:
    title: str
    source: str
    url: str
    period: str = ""
    status: str = ""
    organization: str = ""
    raw_text: str = ""


def load_config() -> dict[str, Any]:
    """config.yaml이 있으면 사용하고, 없으면 config.example.yaml을 기본값으로 사용합니다."""
    path = CONFIG_PATH if CONFIG_PATH.exists() else EXAMPLE_CONFIG_PATH
    with path.open("r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # GitHub Actions Secrets 또는 환경변수로 이메일 설정을 덮어쓸 수 있습니다.
    email_cfg = config.setdefault("notification", {}).setdefault("email", {})
    for key, env_name in {
        "smtp_host": "SMTP_HOST",
        "smtp_port": "SMTP_PORT",
        "sender": "SMTP_SENDER",
        "receiver": "SMTP_RECEIVER",
        "password": "SMTP_PASSWORD",
    }.items():
        if os.getenv(env_name):
            email_cfg[key] = os.getenv(env_name)

    if "smtp_port" in email_cfg:
        email_cfg["smtp_port"] = int(email_cfg["smtp_port"])

    return config


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    response.encoding = response.apparent_encoding or "utf-8"
    return response.text


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def normalize_title(title: str) -> str:
    text = title.lower()
    text = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text)
    text = re.sub(r"20\d{2}년|20\d{2}|\d+차|수정|재공고|추가", " ", text)
    text = re.sub(r"모집|공고|지원사업|참여기업|신청|접수|안내", " ", text)
    text = re.sub(r"[^0-9a-z가-힣]+", "", text)
    return text.strip()


def is_similar(a: str, b: str, threshold: float) -> bool:
    na, nb = normalize_title(a), normalize_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if na in nb or nb in na:
        return True
    return SequenceMatcher(None, na, nb).ratio() >= threshold


def extract_period(text: str) -> str:
    patterns = [
        r"20\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?\s*[~∼\-]\s*20\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?",
        r"\d{4}\.\d{1,2}\.\d{1,2}\s*[~∼\-]\s*\d{4}\.\d{1,2}\.\d{1,2}",
        r"\d{4}-\d{1,2}-\d{1,2}\s*[~∼\-]\s*\d{4}-\d{1,2}-\d{1,2}",
        r"마감일\s*[:：]?\s*\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}",
        r"접수기간\s*[:：]?\s*[^\n|]+",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return clean_text(match.group(0))
    return ""


def detect_status(text: str, status_keywords: list[str]) -> str:
    for keyword in status_keywords:
        if keyword in text:
            return keyword
    return ""


def looks_like_notice_title(text: str) -> bool:
    if len(text) < 8 or len(text) > 180:
        return False
    keywords = ["공고", "모집", "지원", "사업", "창업", "R&D", "연구개발", "참여기업", "신청"]
    return any(k in text for k in keywords)


def parse_notices(source: dict[str, Any]) -> list[Notice]:
    """사이트별 공통 HTML 파싱기입니다.

    정부 사이트의 화면 구조가 조금씩 바뀌어도 최대한 동작하도록
    링크 텍스트와 주변 영역의 텍스트를 함께 분석합니다.
    """
    url = source["url"]
    source_name = source["name"]
    status_keywords = source.get("status_keywords", ["접수중", "모집중"])

    html = fetch_html(url)
    soup = BeautifulSoup(html, "lxml")

    candidates: list[Notice] = []
    seen_links: set[str] = set()

    for a in soup.select("a[href]"):
        title = clean_text(a.get_text(" "))
        if not looks_like_notice_title(title):
            continue

        link = urljoin(url, a.get("href", ""))
        if link in seen_links:
            continue
        seen_links.add(link)

        container = a.find_parent(["li", "tr", "div", "article", "tbody"])
        raw_text = clean_text(container.get_text(" ")) if container else title
        status = detect_status(raw_text, status_keywords)

        # URL 자체가 'ongoing' 또는 schEndAt=N처럼 접수중 목록일 수 있으므로,
        # 상태 단어가 없어도 후보에는 포함합니다.
        period = extract_period(raw_text)

        candidates.append(
            Notice(
                title=title,
                source=source_name,
                url=link,
                period=period,
                status=status or "접수중/모집중 목록",
                raw_text=raw_text[:500],
            )
        )

    return candidates


def deduplicate_notices(notices: list[Notice], threshold: float) -> list[Notice]:
    unique: list[Notice] = []

    for notice in notices:
        duplicated = False
        for idx, existing in enumerate(unique):
            if is_similar(notice.title, existing.title, threshold):
                duplicated = True
                # 같은 공고가 여러 출처에 있으면 출처를 합쳐서 표시합니다.
                sources = set(existing.source.split(" / ")) | {notice.source}
                unique[idx].source = " / ".join(sorted(sources))
                if not unique[idx].period and notice.period:
                    unique[idx].period = notice.period
                if len(notice.url) < len(unique[idx].url):
                    unique[idx].url = notice.url
                break
        if not duplicated:
            unique.append(notice)

    return unique


def load_seen_urls() -> set[str]:
    if not SEEN_PATH.exists():
        return set()
    try:
        return set(json.loads(SEEN_PATH.read_text(encoding="utf-8")))
    except json.JSONDecodeError:
        return set()


def save_seen_urls(urls: set[str]) -> None:
    SEEN_PATH.write_text(json.dumps(sorted(urls), ensure_ascii=False, indent=2), encoding="utf-8")


def build_message(notices: list[Notice]) -> str:
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        f"[정부지원사업 접수중 공고 모니터링]",
        f"조회시각: {today}",
        f"총 {len(notices)}건",
        "",
    ]

    if not notices:
        lines.append("현재 새로 확인된 접수중/모집중 사업공고가 없습니다.")
        return "\n".join(lines)

    for i, n in enumerate(notices, 1):
        lines.extend(
            [
                f"{i}. {n.title}",
                f"- 출처: {n.source}",
                f"- 상태: {n.status or '-'}",
                f"- 접수기간/마감: {n.period or '페이지 확인 필요'}",
                f"- 링크: {n.url}",
                "",
            ]
        )
    return "\n".join(lines)


def send_email(config: dict[str, Any], subject: str, body: str) -> None:
    email_cfg = config.get("notification", {}).get("email", {})
    sender = email_cfg.get("sender")
    receiver = email_cfg.get("receiver")
    password = email_cfg.get("password")
    smtp_host = email_cfg.get("smtp_host", "smtp.gmail.com")
    smtp_port = int(email_cfg.get("smtp_port", 587))

    if not sender or not receiver or not password:
        print("[알림 생략] 이메일 sender/receiver/password 설정이 부족합니다.")
        print(body)
        return

    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = receiver

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)


def run() -> None:
    config = load_config()
    all_notices: list[Notice] = []

    for source in config.get("sources", []):
        try:
            notices = parse_notices(source)
            print(f"[{source['name']}] {len(notices)}건 수집")
            all_notices.extend(notices)
        except Exception as e:
            print(f"[{source.get('name', 'unknown')}] 수집 실패: {e}")

    threshold = float(config.get("deduplication", {}).get("similarity_threshold", 0.88))
    unique_notices = deduplicate_notices(all_notices, threshold)

    # 이미 보낸 URL은 제외합니다. 첫 실행 때는 전체가 발송될 수 있습니다.
    seen_urls = load_seen_urls()
    for notice in unique_notices:
        if notice.url in seen_urls:
            notice.status = f"기존 / {notice.status}"
        else:
            notice.status = f"신규 / {notice.status}"
    
    new_notices = [n for n in unique_notices if n.url not in seen_urls]

    subject = f"정부지원사업 공고 신규 {len(new_notices)}건 / 전체 {len(unique_notices)}건"
    body = build_message(unique_notices)

    print(body)

    method = config.get("notification", {}).get("method", "email")
    if method == "email":
        send_email(
            config["notification"]["email"],
            subject,
            body,
        )

    elif method == "slack":
        send_slack_message(
            config["notification"]["slack"],
            subject,
            body,
        )

    else:
        raise ValueError(f"지원하지 않는 알림 방식입니다: {method}")

    all_urls = seen_urls | {n.url for n in unique_notices}
    save_seen_urls(all_urls)

    # GitHub Actions 로그/아티팩트 확인용 JSON 저장
    output_path = BASE_DIR / "latest_notices.json"
    output_path.write_text(
        json.dumps([asdict(n) for n in new_notices], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    run()
