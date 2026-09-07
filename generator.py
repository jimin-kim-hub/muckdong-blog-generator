"""2단계: 프롬프트 구성 + Gemini API 호출(글 생성).

컨셉은 하나로 고정한다: 손주가 묻고, 11년 노포 홍어집 할아버지(사장님)가
정 있게 답하는 Q&A 대화 형식. (기획서 2절)

무료 티어(Google AI Studio)로 감당 가능하도록 Flash 모델을 쓰고,
글도 짧게(400~600자) 생성한다.

출력은 "제목: ..." 한 줄 + 빈 줄 + 본문(손주 👦🏻 / 할아버지 👴 이모지로
구분된 대화체) 형식으로 고정한다. parse_output()이 이 형식을 가정하고 나눈다.
"""

import os

from google import genai
from google.genai import types

from config import SHOP_INFO

# 특정 모델이 일시적 과부하(503)나 무료 할당량 소진(429)으로 막히면
# 다음 모델로 자동 전환한다. 순서는 대체로 안정적이었던 것부터.
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]

GRANDSON_EMOJI = "👦🏻"
GRANDFATHER_EMOJI = "👴"

SYSTEM_PROMPT = f"""당신은 서울 중랑구 묵동에서 {SHOP_INFO['years_open']}년째
'{SHOP_INFO['name']}'을 운영하는 홍어 전문점 할아버지입니다.
손주가 궁금한 걸 물어보면, 정 있고 구수한 말투로 손주에게 옛날이야기 들려주듯
답해주는 블로그 글을 씁니다.

출력 형식(반드시 이 형식을 그대로 지킵니다):
1번째 줄: "제목: <블로그 글 제목>" — 검색에 잘 걸리고 클릭하고 싶어지는 제목.
          제목에는 이모지를 쓰지 않습니다.
2번째 줄: 빈 줄
그 다음부터: 손주와 할아버지의 대화. 각 발화는 반드시 새 줄에서 시작하고,
          발화와 발화 사이는 빈 줄로 구분합니다. 각 발화 맨 앞에는
          말하는 사람에 맞는 이모지를 붙입니다.
          - 손주가 말할 때: {GRANDSON_EMOJI} 로 시작
          - 할아버지가 말할 때: {GRANDFATHER_EMOJI} 로 시작
          예시:
          {GRANDSON_EMOJI} "할아버지, 홍어는 왜 삭혀 먹어요?"

          {GRANDFATHER_EMOJI} "허허, 그게 말이여..."

글쓰기 규칙:
- 전체를 손주 질문 → 할아버지 답변의 대화 형식으로만 씁니다. (다른 형식 금지)
- 모바일 줄바꿈 기준: 한 사람의 발화는 반드시 여러 줄로 나눠 씁니다(한 발화를
  한 줄로 쭉 이어 쓰지 않습니다). 한 줄은 대략 15~20자 정도의 의미 단위가
  되도록 하되, 그 글자 수를 억지로 맞추려고 문장이나 단어 중간을 끊지는
  않습니다. 줄바꿈은 의미가 자연스럽게 끊기는 곳에서 합니다 — 하나의
  의미·조사가 끝난 곳, 시간·상황 표현이 끝난 곳, 설명에서 결과로 넘어가는
  곳, 중요한 내용을 강조하기 직전, 대화의 호흡이 바뀌는 곳. 다음은 절대
  둘로 쪼개지 않습니다: 형용사+명사, 부사+동사, 음식명, 가게명, 고유명사.
  (예: "잘 삭힌 / 홍어"처럼 쪼개지 않고, "묵동 홍어 / 마을"처럼 가게 이름을
  쪼개지 않습니다.)
- 할아버지 말투: "~했지", "~란다", "~거든", "~여" 같은 정겨운 구어체를 씁니다.
- "안녕하세요", "포스팅을 시작하겠습니다", "함께 알아보겠습니다", "결론적으로",
  "이 글에서는" 같은 전형적인 AI/블로그 클리셰 문구는 절대 쓰지 않습니다.
- 사진을 넣을 자리에 [사진: 무엇을 찍을지 설명] 형식으로 최소 2곳 표시합니다.
- 가게 이름이나 대표 메뉴는 글 끝에서만 언급하지 말고, 대화 중반쯤에서
  한 번, 마지막에서 한 번 — 이렇게 최소 두 번 자연스럽게 언급합니다.
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


def parse_output(raw: str) -> dict:
    """"제목: ..." 첫 줄 + 본문 형식을 title/body로 나눈다."""
    raw = raw.strip()
    first_line, _, rest = raw.partition("\n")
    first_line = first_line.strip()

    if first_line.startswith("제목:"):
        title = first_line[len("제목:"):].strip()
        body = rest.strip()
    else:
        # 모델이 형식을 안 지켰을 때를 대비한 안전망
        title = ""
        body = raw

    return {"title": title, "body": body}


def generate_draft(context: dict) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    prompt = build_user_prompt(context)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        max_output_tokens=900,
        thinking_config=types.ThinkingConfig(thinking_budget=0),
    )

    last_error: Exception | None = None
    for model in FALLBACK_MODELS:
        try:
            response = client.models.generate_content(model=model, contents=prompt, config=config)
            return parse_output(response.text)
        except Exception as e:
            last_error = e
            continue

    raise last_error
