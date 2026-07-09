from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET

from dataclasses import dataclass, asdict
from typing import Any

import requests

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
    """후보 필드명 중 처음으로 값이 있는 필드를 반환합니다."""
    for key in candidates:
        if key in item and item[key] not in (None, ""):
            return str(item[key]).strip()
    return ""


def _dig_items(data: Any) -> list[dict[str, Any]]:
    """공공데이터 JSON 응답에서 item 리스트를 최대한 유연하게 찾아냅니다."""
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if not isinstance(data, dict):
        return []

    # 흔한 공공데이터 구조: response.body.items.item
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

    # 그래도 못 찾으면 dict 안쪽에서 list[dict]를 재귀적으로 탐색
    for value in data.values():
        found = _dig_items(value)
        if found:
            return found
    return []


def _make_detail_url(template: str, notice_id: str) -> str:
    if not template or not notice_id:
        return ""
    return template.replace("{id}", notice_id)


def _normalize_date(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    # 20260709 -> 2026-07-09
    if re.fullmatch(r"\d{8}", value):
        return f"{value[:4]}-{value[4:6]}-{value[6:8]}"
    return value

def _normalize_url(value: str) -> str:
    value = (value or "").strip()

    if not value:
        return ""

    # API 문서 예시 중 web/contents가 중복되는 경우 보정
    value = value.replace("/web/contents/web/contents/", "/web/contents/")

    # www.k-startup.go.kr 로 시작하면 https:// 붙이기
    if value.startswith("www."):
        value = "https://" + value

    # 혹시 javascript:go_view(178453); 형태가 들어오면 상세 URL로 변환
    match = re.search(r"go_view\((\d+)\)", value)
    if match:
        pbanc_sn = match.group(1)
        return (
            "https://www.k-startup.go.kr/web/contents/"
            f"bizpbanc-ongoing.do?schM=view&pbancSn={pbanc_sn}"
        )

    return value


def _contains_any_keyword(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return True
    return any(keyword in text for keyword in keywords)


def build_api_params(config: dict[str, Any]) -> dict[str, Any]:
    """config.yaml 기준으로 API 요청 파라미터를 구성합니다."""
    kcfg = config["kstartup"]
    params = dict(kcfg.get("params", {}))

    service_key = os.getenv("KSTARTUP_SERVICE_KEY") or kcfg.get("service_key", "")
    if service_key:
               # K-Startup 서비스설계서 기준 필수 파라미터명은 ServiceKey입니다.
        params.setdefault("ServiceKey", service_key)


    return params


def fetch_kstartup_notices(config: dict[str, Any]) -> list[Notice]:
    """K-Startup 지원 사업 공고 API를 호출하고 Notice 목록으로 정규화합니다."""
    kcfg = config["kstartup"]
    api_url = kcfg.get("api_url", "").strip()
    if not api_url:
        raise ValueError("config.yaml의 kstartup.api_url 값이 비어 있습니다. 공공데이터포털 Swagger의 요청 URL을 입력하세요.")

    params = build_api_params(config)

    response = requests.get(api_url, params=params, timeout=25)
    response.raise_for_status()

    text = response.text.strip()
    try:
        data = response.json()
        items = _dig_items(data)
    except Exception:
          # JSON이 아니면 XML로 한 번 더 시도합니다.
        if text.startswith("<"):
            items = _parse_xml_items(text)
        else:
            raise RuntimeError(
                "API 응답이 JSON/XML 형식이 아닙니다. "
                "API URL/인증키/파라미터를 확인하세요. 응답 앞부분: " + text[:300]
            )
   
    field_candidates = kcfg.get("field_candidates", {})
    include_keywords = kcfg.get("include_keywords", [])
    detail_template = kcfg.get("detail_url_template", "")

    notices: list[Notice] = []
    for item in items:
        notice_id = _first_value(item, field_candidates.get("id", []))
        title = _first_value(item, field_candidates.get("title", []))
        category = _first_value(item, field_candidates.get("category", []))
        organization = _first_value(item, field_candidates.get("organization", []))
        start_date = _normalize_date(_first_value(item, field_candidates.get("start_date", [])))
        end_date = _normalize_date(_first_value(item, field_candidates.get("end_date", [])))
        status = _normalize_status(_first_value(item, field_candidates.get("status", [])))
        url = _first_value(item, field_candidates.get("url", [])) or _make_detail_url(detail_template, notice_id)
        url = _normalize_url(url)

        combined_text = " ".join(str(v) for v in item.values() if v is not None)
        if not _contains_any_keyword(combined_text, include_keywords):
            continue

        # 제목이 없으면 Slack 알림 가치가 낮으므로 제외합니다.
        if not title:
            continue

        # ID가 없으면 제목+마감일을 임시 ID로 사용합니다.
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

    return notices

def _parse_xml_items(xml_text: str) -> list[dict[str, Any]]:
    """K-Startup XML 응답을 list[dict] 형태로 변환합니다.

    응답 예:
    <results>
      <data>
        <item>
          <col name="biz_pbanc_nm">공고명</col>
        </item>
      </data>
    </results>
    """
    root = ET.fromstring(xml_text)
    items: list[dict[str, Any]] = []

    for item_el in root.findall(".//item"):
        item: dict[str, Any] = {}

        # 형태 1: <item><col name="필드명">값</col></item>
        for col in item_el.findall("col"):
            name = col.attrib.get("name")
            if name:
                item[name] = (col.text or "").strip()

        # 형태 2: <item><biz_pbanc_nm>값</biz_pbanc_nm></item>
        for child in list(item_el):
            if child.tag != "col":
                item[child.tag] = (child.text or "").strip()

        if item:
            items.append(item)

    return items

def _normalize_status(value: str) -> str:
    value = (value or "").strip().upper()

    if value == "Y":
        return "모집중"
    if value == "N":
        return "마감"
    return value
