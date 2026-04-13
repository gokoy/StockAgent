from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import requests

from app.models.schemas import NewsItem


CORP_CODE_URL = "https://opendart.fss.or.kr/api/corpCode.xml"
DISCLOSURE_LIST_URL = "https://opendart.fss.or.kr/api/list.json"
IMPORTANT_DISCLOSURE_KEYWORDS = (
    "잠정실적",
    "영업실적",
    "실적",
    "수주",
    "공급계약",
    "단일판매ㆍ공급계약체결",
    "유상증자",
    "무상증자",
    "전환사채",
    "신주인수권부사채",
    "BW",
    "CB",
    "자기주식",
    "최대주주",
    "대표이사",
    "합병",
    "분할",
    "영업정지",
    "횡령",
    "배임",
    "관리종목",
    "상장폐지",
)


def fetch_recent_disclosures(
    ticker: str,
    name: str,
    max_age_hours: int,
    api_key: str | None,
    cache_path: Path,
    limit: int = 5,
) -> list[NewsItem]:
    if not api_key or not ticker.endswith(".KS"):
        return []
    corp_code = _lookup_corp_code(api_key, ticker, cache_path)
    if not corp_code:
        return []
    now = datetime.now(UTC)
    start = (now - timedelta(hours=max_age_hours)).strftime("%Y%m%d")
    end = now.strftime("%Y%m%d")
    try:
        response = requests.get(
            DISCLOSURE_LIST_URL,
            params={
                "crtfc_key": api_key,
                "corp_code": corp_code,
                "bgn_de": start,
                "end_de": end,
                "page_count": "30",
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception:
        return []
    if str(payload.get("status")) != "000":
        return []
    items: list[NewsItem] = []
    for row in payload.get("list", []):
        report_name = str(row.get("report_nm", "")).strip()
        if not _is_important_disclosure(report_name):
            continue
        receipt_no = str(row.get("rcept_no", "")).strip()
        receipt_date = str(row.get("rcept_dt", "")).strip()
        if not receipt_no or len(receipt_date) != 8:
            continue
        published_at = datetime.strptime(receipt_date, "%Y%m%d").replace(tzinfo=UTC)
        items.append(
            NewsItem(
                headline=f"[공시] {report_name}",
                summary=f"{name} 관련 공시. 제출인: {row.get('flr_nm', '')}",
                published_at=published_at,
                source="OpenDART",
                url=f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={receipt_no}",
            )
        )
        if len(items) >= limit:
            break
    return items


def _lookup_corp_code(api_key: str, ticker: str, cache_path: Path) -> str | None:
    mapping = _load_corp_code_cache(api_key, cache_path)
    normalized = ticker.replace(".KS", "").replace(".KQ", "")
    return mapping.get(normalized)


def _load_corp_code_cache(api_key: str, cache_path: Path) -> dict[str, str]:
    if cache_path.exists():
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                return {str(key): str(value) for key, value in payload.items()}
        except Exception:
            pass
    mapping = _download_corp_codes(api_key)
    if mapping:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")
    return mapping


def _download_corp_codes(api_key: str) -> dict[str, str]:
    try:
        response = requests.get(CORP_CODE_URL, params={"crtfc_key": api_key}, timeout=30)
        response.raise_for_status()
        with ZipFile(BytesIO(response.content)) as archive:
            xml_bytes = archive.read("CORPCODE.xml")
        root = ET.fromstring(xml_bytes)
    except Exception:
        return {}
    mapping: dict[str, str] = {}
    for item in root.findall("list"):
        stock_code = (item.findtext("stock_code") or "").strip()
        corp_code = (item.findtext("corp_code") or "").strip()
        if stock_code and corp_code:
            mapping[stock_code] = corp_code
    return mapping


def _is_important_disclosure(report_name: str) -> bool:
    return any(keyword in report_name for keyword in IMPORTANT_DISCLOSURE_KEYWORDS)
