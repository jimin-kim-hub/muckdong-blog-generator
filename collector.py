"""1단계: 날씨·계절·공휴일·키워드 수집.

가벼운 최적화 결정:
- 기상청 단기예보 API는 공공데이터포털 서비스키 발급이 필요해, 키 없이도
  바로 동작하는 Open-Meteo(무료, 키 불필요)를 1차 소스로 사용한다.
- 특일정보 API 대신 `holidays` 라이브러리(오프라인, 키 불필요)로 대체한다.
- 두 외부 호출 모두 실패해도 서비스가 죽지 않도록 안전한 기본값을 반환한다.
"""

import random
from datetime import date

import holidays
import requests

from config import POPULAR_KEYWORDS

# 묵동(서울 중랑구) 대략 좌표
MUKDONG_LAT = 37.6115
MUKDONG_LON = 127.0764

WEATHER_CODE_KR = {
    0: "맑음", 1: "대체로 맑음", 2: "구름 조금", 3: "흐림",
    45: "안개", 48: "짙은 안개",
    51: "약한 이슬비", 53: "이슬비", 55: "강한 이슬비",
    61: "약한 비", 63: "비", 65: "강한 비",
    71: "약한 눈", 73: "눈", 75: "강한 눈",
    80: "소나기", 81: "소나기", 82: "강한 소나기",
    95: "뇌우", 96: "뇌우(우박 동반)", 99: "강한 뇌우(우박 동반)",
}


def get_weather() -> dict:
    """오늘 날씨를 가져온다. 실패 시 안전한 기본값을 반환한다."""
    try:
        resp = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": MUKDONG_LAT,
                "longitude": MUKDONG_LON,
                "current": "temperature_2m,weather_code",
                "timezone": "Asia/Seoul",
            },
            timeout=5,
        )
        resp.raise_for_status()
        current = resp.json()["current"]
        code = current.get("weather_code")
        return {
            "temperature": round(current["temperature_2m"]),
            "condition": WEATHER_CODE_KR.get(code, "변화무쌍한 날씨"),
            "available": True,
        }
    except Exception:
        return {"temperature": None, "condition": "선선한 날씨", "available": False}


def get_season_phrase(today: date | None = None) -> str:
    today = today or date.today()
    month = today.month
    if month in (3, 4, 5):
        return "봄"
    if month in (6, 7, 8):
        return "여름"
    if month in (9, 10, 11):
        return "가을"
    return "겨울"


def get_holiday_name(today: date | None = None) -> str | None:
    today = today or date.today()
    kr_holidays = holidays.KR(years=today.year)
    return kr_holidays.get(today)


def get_popular_keyword() -> str:
    return random.choice(POPULAR_KEYWORDS)


def collect_context(keyword: str | None = None) -> dict:
    """4개 소스를 한 번에 모아 글 생성에 필요한 컨텍스트를 만든다.

    keyword를 직접 지정하면 그 키워드/주제를 쓰고, 비워두면
    POPULAR_KEYWORDS 중 하나를 자동으로 고른다.
    """
    today = date.today()
    return {
        "date": today.isoformat(),
        "season": get_season_phrase(today),
        "weather": get_weather(),
        "holiday": get_holiday_name(today),
        "keyword": keyword.strip() if keyword and keyword.strip() else get_popular_keyword(),
    }
