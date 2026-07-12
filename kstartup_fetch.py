from __future__ import annotations

import json
import os
import re
import time
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import date, datetime
from html import unescape
from typing import Any

import requests


ALLOWED_CATEGORIES = {
    "사업화",
    "인력",
    "멘토링ㆍ컨설팅ㆍ교육",
}


@dataclass
class Notice:
    notice_id: str
    title: str
    category: str = ""
    organization: str = ""
    start_date: str = ""
    end_date: str = ""
    status: str = ""
    url: str = ""
    raw: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _first_value(item: dict[str, Any], candidates: list[str]) -> str:
    for key in candidates:
        if key in item and item[key] not in (None, ""):
            return str(item[key]).strip()
    return ""


def _dig_items(data: Any) -> list[dict[str, Any]]:
    """K-Startup JSON 응답에서 item 리스트를 최대한 유연하게 찾아냅니다."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    paths = [
        ["response", "body", "items", "item"],
        ["response", "body", "item"],
        ["body", "items", "item"],
        ["body", "item"],
        ["items", "item"],
        ["items"],
        ["data"],
        ["result"],
        ["list"],
    ]

    for path in paths:
        cur: Any = data
        for key in path:
            if isinstance(cur, dict) and key in cur:
                cur = cur[key]
            else:
                cur = None
                break

        if cur is None:
            continue

        if isinstance(cur, dict):
            return [cur]

        if isinstance(cur, list):
            return [x for x in cur if isinstance(x, dict)]

    for value in data.values():
        found = _dig_items(value)
        if found:
            return found

    return []


def _parse_xml_items(xml_text: str) -> list[dict[str, Any]]:
    """K-Startup XML 응답을 list[dict] 형태로 변환합니다."""
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []

    for item_el in root.findall(".//item"):
        item: dict[str, Any] = {}

        for col in item_el.findall("col"):
            name = col.attrib.get("name")
            if name:
                item[name] = unescape((col.text or "").strip())

        for child in list(item_el):
            if child.tag != "col":
                item[child.tag] = unescape((child.text or "").strip())

        if item:
            items.append(item)

    return items


def _make_detail_url(template: str, notice_id: str) -> str:
    if not template or not notice_id:
        return ""
    return template.replace("{id}", notice_id)


def _normalize_date(value: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    value = value.replace(".", "-").replace("/", "-")

    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"

    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value

    # 날짜 뒤에 시간이 붙어 오는 경우 앞 10자리만 사용합니다.
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if match:
        return match.group(0)

    return value


def _normalize_url(value: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    value = unescape(value)
    value = value.replace("/web/contents/web/contents/", "/web/contents/")

    match = re.search(r"go_view\((\d+)\)", value)
    if match:
        pbanc_sn = match.group(1)
        return (
            "https://www.k-startup.go.kr/web/contents/"
            f"bizpbanc-ongoing.do?schM=view&pbancSn={pbanc_sn}"
        )

    if value.startswith("//"):
        return "https:" + value

    if value.startswith("/"):
        return "https://www.k-startup.go.kr" + value

    if value.startswith("www."):
        return "https://" + value

    return value


def _normalize_status(value: str) -> str:
    value = (value or "").strip().upper()

    if value == "Y":
        return "모집중"
    if value == "N":
        return "마감"
    return value


def _parse_date(value: str) -> date | None:
    value = _normalize_date(value)

    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _is_active_notice(status: str, end_date: str) -> bool:
    """마감 공고 또는 접수 마감일이 지난 공고는 제외합니다."""
    if status == "마감":
        return False

    end = _parse_date(end_date)

    if end is None:
        return True

    return end >= date.today()


def _contains_any_keyword(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return any(keyword in text for keyword in keywords)


def request_with_retry(api_url: str, params: dict[str, Any], max_retries: int = 3) -> requests.Response:
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            response = requests.get(
                api_url,
                params=params,
                timeout=60,
                headers={
                    "User-Agent": "Mozilla/5.0 GovMonitoringBot/1.0",
                    "Accept": "application/json, text/plain, */*",
                },
            )
            response.raise_for_status()
            return response

        except requests.exceptions.ConnectTimeout as exc:
            last_error = exc
            print(f"[경고] K-Startup API 연결 시간 초과: {attempt}/{max_retries}회 재시도")

        except requests.exceptions.ReadTimeout as exc:
            last_error = exc
            print(f"[경고] K-Startup API 응답 시간 초과: {attempt}/{max_retries}회 재시도")

        except requests.exceptions.RequestException as exc:
            last_error = exc
            print(f"[경고] K-Startup API 요청 실패: {attempt}/{max_retries}회 재시도 - {exc}")

        time.sleep(5 * attempt)

    raise RuntimeError(f"K-Startup API 요청이 {max_retries}회 모두 실패했습니다: {last_error}")


def build_api_params(config: dict[str, Any]) -> dict[str, Any]:
    kcfg = config["kstartup"]
    params = dict(kcfg.get("params", {}))

    service_key = os.getenv("KSTARTUP_SERVICE_KEY") or kcfg.get("service_key", "")
    if service_key:
        params.setdefault("ServiceKey", service_key)

    return params


def fetch_kstartup_notices(config: dict[str, Any]) -> list[Notice]:
    """K-Startup 지원사업 공고 API를 호출하고 Notice 목록으로 정규화합니다."""
    kcfg = config["kstartup"]
    api_url = kcfg.get("api_url", "").strip()

    if not api_url:
        raise ValueError("config.yaml의 kstartup.api_url 값이 비어 있습니다.")

    params = build_api_params(config)
    response = request_with_retry(api_url, params)

    text = response.text.strip()

    try:
        data = response.json()
        items = _dig_items(data)
    except Exception:
        if text.startswith("<"):
            items = _parse_xml_items(text)
        else:
            raise RuntimeError(
                "K-Startup API 응답이 JSON/XML 형식이 아닙니다. "
                "API URL/인증키/파라미터를 확인하세요. 응답 앞부분: " + text[:300]
            )

    field_candidates = kcfg.get("field_candidates", {})
    include_keywords = kcfg.get("include_keywords", [])
    detail_template = kcfg.get("detail_url_template", "")
    allowed_categories = set(kcfg.get("allowed_categories", [])) or ALLOWED_CATEGORIES

    notices: list[Notice] = []

    for item in items:
        notice_id = _first_value(item, field_candidates.get("id", []))
        title = _first_value(item, field_candidates.get("title", []))
        category = _first_value(item, field_candidates.get("category", []))

        if category not in allowed_categories:
            continue

        organization = _first_value(item, field_candidates.get("organization", []))
        start_date = _normalize_date(_first_value(item, field_candidates.get("start_date", [])))
        end_date = _normalize_date(_first_value(item, field_candidates.get("end_date", [])))
        status = _normalize_status(_first_value(item, field_candidates.get("status", [])))
        url = _first_value(item, field_candidates.get("url", [])) or _make_detail_url(detail_template, notice_id)
        url = _normalize_url(url)

        if not _is_active_notice(status, end_date):
            continue

        combined_text = " ".join(str(v) for v in item.values() if v is not None)
        if not _contains_any_keyword(combined_text, include_keywords):
            continue

        if not title:
            continue

        if not notice_id:
            notice_id = f"{title}|{end_date}|{url}"

        notices.append(
            Notice(
                notice_id=notice_id,
                title=title,
                category=category,
                organization=organization,
                start_date=start_date,
                end_date=end_date,
                status=status,
                url=url,
                raw=item,
            )
        )

    return sorted(
        notices,
        key=lambda n: (n.end_date or "9999-12-31", n.title),
    )
