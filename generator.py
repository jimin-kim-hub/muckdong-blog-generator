"""2단계: 프롬프트 구성 + Gemini API 호출(글 생성).

컨셉은 하나로 고정한다: 손주가 묻고, 11년 노포 홍어집 할아버지(사장님)가
정 있게 답하는 Q&A 대화 형식. (기획서 2절)

무료 티어(Google AI Studio)로 감당 가능하도록 Flash 모델을 쓰고,
글도 짧게(400~600자) 생성한다.
"""

import os

from google import genai
from google.genai import types

from config import SHOP_INFO

MODEL = "gemini-3.5-flash"

SYSTEM_PROMPT = f"""당신은 서울 중랑구 묵동에서 {SHOP_INFO['years_open']}년째
'{SHOP_INFO['name']}'을 운영하는 홍어 전문점 할아버지입니다.
손주가 궁금한 걸 물어보면, 정 있고 구수한 말투로 손주에게 옛날이야기 들려주듯
답해주는 블로그 글을 씁니다.

글쓰기 규칙:
- 전체를 손주 질문 → 할아버지 답변의 대화 형식으로만 씁니다. (다른 형식 금지)
- 할아버지 말투: "~했지", "~란다", "~거든", "~여" 같은 정겨운 구어체를 씁니다.
- "안녕하세요", "포스팅을 시작하겠습니다", "함께 알아보겠습니다", "결론적으로",
  "이 글에서는" 같은 전형적인 AI/블로그 클리셰 문구는 절대 쓰지 않습니다.
- 사진을 넣을 자리에 [사진: 무엇을 찍을지 설명] 형식으로 최소 2곳 표시합니다.
- 글 안에 가게 이름과 대표 메뉴를 자연스럽게 최소 한 번씩 언급합니다.
- 마지막은 손주가 아니라 할아버지의 말로 자연스럽게 마무리합니다(초대 인사 등).
- 분량은 공백 포함 400~600자로 짧고 간결하게 씁니다. 군더더기 설명 없이 핵심만.
"""


def build_user_prompt(context: dict) -> str:
    weather = context["weather"]
    if weather.get("available") and weather.get("temperature") is not None:
        weather_line = f"오늘 날씨: {weather['condition']}, 기온 약 {weather['temperature']}도"
    else:
        weather_line = f"오늘 날씨: {weather['condition']}"

    holiday_line = f"\n오늘은 '{context['holiday']}'입니다. 자연스럽게 언급해도 좋습니다." if context.get("holiday") else ""

    menu_str = ", ".join(SHOP_INFO["menu"])

    return f"""오늘 정보:
- 날짜: {context['date']} ({context['season']})
- {weather_line}{holiday_line}
- 오늘 글의 키워드/주제: '{context['keyword']}' — 이 단어를 손주의 질문이나 할아버지의 답변 속에 자연스럽게 최소 한 번 넣어주세요.

가게 정보:
- 상호: {SHOP_INFO['name']}
- 대표 메뉴: {menu_str}

위 정보를 반영해서, 손주가 '{context['keyword']}'와 관련된 질문을 하고
할아버지가 답하는 블로그 글 초안을 한 편 써주세요."""


def generate_draft(context: dict) -> str:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=MODEL,
        contents=build_user_prompt(context),
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=800,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    return response.text.strip()
