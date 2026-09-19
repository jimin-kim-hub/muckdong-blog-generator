"""네이버 검색광고 키워드도구 API 연동.

가벼운 최적화 결정: 매 요청마다 부르지 않고 하루 1회만 호출해 캐싱한다.
키가 없거나 호출이 실패해도 예외를 밖으로 내보내지 않는다 — 호출부
(collector.get_popular_keyword)가 정적 목록으로 자연스럽게 폴백한다.

API 문서: https://naver.github.io/searchad-apidoc/
"""

import base64
import hashlib
import hmac
import logging
import os
import random
import time
from datetime import date

import requests

API_URL = "https://api.searchad.naver.com/keywordstool"
URI = "/keywordstool"

# hintKeywords는 한 번에 최대 5개까지만 보낼 수 있다. 매번 같은 5개를
# 보내면 하루 1회 캐싱 특성상 후보군이 계속 똑같아지므로, 이 풀에서
# 매일(캐시가 갱신될 때) 5개를 무작위로 뽑아 보낸다 — 날마다 다른 조합의
# 연관 키워드가 나오게 하기 위함. hintKeywords는 키워드 안에 공백이
# 있으면 400을 반환하므로 전부 붙여 쓴다.
SEED_KEYWORD_POOL = [
    "홍어", "묵동홍어", "홍어삼합", "홍어무침", "홍어애탕",
    "삭힌홍어", "홍어회", "홍어탕", "중랑구홍어", "먹골역홍어",
]
SEEDS_PER_CALL = 5
TOP_N = 15

# 네이버 키워드도구는 "홍어"처럼 넓은 시드에 대해 전국 단위로 느슨하게
# 연관된 키워드(다른 지역 맛집 등)까지 섞어 준다. 이 중 하나라도 포함된
# 키워드만 남겨 주제에서 벗어나지 않게 한다.
RELEVANCE_TERMS = ["홍어", "묵동", "중랑구", "먹골"]


def _is_relevant(keyword: str) -> bool:
    return any(term in keyword for term in RELEVANCE_TERMS)

logger = logging.getLogger("uvicorn.error")

_cache: dict = {"date": None, "keywords": []}


def _signature(timestamp: str, method: str, uri: str, secret_key: str) -> str:
    message = f"{timestamp}.{method}.{uri}"
    digest = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    return base64.b64encode(digest).decode()


def _headers() -> dict:
    api_key = os.environ["NAVER_API_KEY"]
    secret_key = os.environ["NAVER_SECRET_KEY"]
    customer_id = os.environ["NAVER_CUSTOMER_ID"]
    timestamp = str(round(time.time() * 1000))
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": api_key,
        "X-Customer": customer_id,
        "X-Signature": _signature(timestamp, "GET", URI, secret_key),
    }


def _parse_count(value) -> float:
    """모바일/PC 검색량은 숫자 또는 "< 10" 같은 문자열로 온다."""
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("<"):
            return 5.0
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return 0.0
    return 0.0


def fetch_keywords() -> list[str]:
    """시드 풀에서 5개를 무작위로 뽑아 연관 키워드를 모바일 검색량 순으로
    정렬해 상위 TOP_N개를 반환한다."""
    seeds = random.sample(SEED_KEYWORD_POOL, min(SEEDS_PER_CALL, len(SEED_KEYWORD_POOL)))
    resp = requests.get(
        API_URL,
        params={"hintKeywords": ",".join(seeds), "showDetail": 1},
        headers=_headers(),
        timeout=8,
    )
    if not resp.ok:
        # 네이버가 돌려주는 에러 본문(코드·사유)까지 로그에 남겨서 원인을 바로 알 수 있게 한다.
        logger.error("네이버 키워드도구 응답 오류 %s: %s", resp.status_code, resp.text[:500])
    resp.raise_for_status()
    items = resp.json().get("keywordList", [])
    items = [item for item in items if _is_relevant(item.get("relKeyword", ""))]

    items.sort(key=lambda item: _parse_count(item.get("monthlyMobileQcCnt")), reverse=True)
    keywords = [item["relKeyword"] for item in items if item.get("relKeyword")]
    return keywords[:TOP_N]


def get_cached_keywords() -> list[str]:
    """하루 1회만 실제 API를 부르고, 나머지는 캐시된 값을 쓴다.
    NAVER_* 환경변수가 없거나 호출이 실패하면 조용히 빈 목록을 반환한다."""
    today = date.today().isoformat()
    if _cache["date"] == today:
        return _cache["keywords"]

    if not all(os.environ.get(k) for k in ("NAVER_API_KEY", "NAVER_SECRET_KEY", "NAVER_CUSTOMER_ID")):
        return []

    try:
        keywords = fetch_keywords()
        _cache["date"] = today
        _cache["keywords"] = keywords
        logger.info("네이버 키워드도구 조회 성공: %d개", len(keywords))
        return keywords
    except Exception:
        logger.exception("네이버 키워드도구 조회 실패 — 정적 키워드로 폴백")
        return []
