"""2단계: 프롬프트 구성 + Gemini API 호출(글 생성).

2026-09 방문 피드백 반영: '할아버지가 손주에게' 가족 롤플레이 컨셉은
폐기. 사장님(전문가)이 직접 정보를 들려주는 톤으로 바꿨다.
구조는 세 가지 중 고를 수 있다(기본은 expert).
- expert: 흔한 오해를 짚고 원리·실전 팁으로 이어지는 정보형 (길고 태그 포함)
- qna: Q&A 인터뷰 형식 (질문/답변, 가족 설정 없음)
- column: Q&A 없이 짧은 문단이 이어지는 칼럼/매거진 형식

허구 생성 차단: 가상의 손님·장면·대화·일화를 지어내지 않도록 프롬프트에
명시한다. 그래도 완전히 막히지는 않으므로 화면의 발행 전 체크리스트로
사람이 최종 확인한다.

출력은 "제목: ..." 한 줄 + 빈 줄 + 본문 형식으로 고정한다.
parse_output()이 이 형식을 가정하고 나눈다.
"""

import os

from google import genai
from google.genai import types

from config import SHOP_INFO

# 특정 모델이 일시적 과부하(503)나 무료 할당량 소진(429)으로 막히면
# 다음 모델로 자동 전환한다. 순서는 대체로 안정적이었던 것부터.
FALLBACK_MODELS = ["gemini-3.5-flash", "gemini-3.6-flash", "gemini-3.1-flash-lite"]

CONCEPTS = ("expert", "qna", "column")
DEFAULT_CONCEPT = "expert"

# expert 컨셉은 글이 길고 태그까지 뽑으므로 출력 토큰을 더 준다.
MAX_OUTPUT_TOKENS = {"expert": 2000, "qna": 900, "column": 900}

_COMMON_HEADER = f"""당신은 서울 중랑구 묵동에서 {SHOP_INFO['years_open']}년째
'{SHOP_INFO['name']}'을 운영해 온 홍어 전문가입니다.
오래 다뤄본 사람만 아는 정보를 차분하게 풀어주는 글을 씁니다.
40~60대는 편하게 읽을 수 있지만, 20~30대가 봐도 세련되게 느껴지는
문장과 정보를 담습니다. 아이에게 옛날이야기 들려주는 듯한 말투나
가족 설정은 쓰지 않습니다.
"""

_NO_FICTION_RULES = """
사실 원칙(가장 중요):
- 이야기를 지어내지 않습니다. 가상의 손님, 없었던 장면, 만들어낸 대화,
  지어낸 일화는 절대 쓰지 않습니다.
- 대신 '오래 다뤄본 사람의 관점'으로 씁니다. 판단 기준, 자주 받는 질문,
  흔한 오해, 고르는 요령처럼 경험에서 나오는 실질적인 정보를 씁니다.
- 검증할 수 없는 구체적 수치나 사건(몇 명이 왔다, 언제 무슨 일이 있었다,
  매일 무엇을 한다 같은 운영 방식 서술)은 지어내지 않습니다.
"""

_COMMON_RULES = _NO_FICTION_RULES + """
공통 규칙:
- "안녕하세요", "포스팅을 시작하겠습니다", "함께 알아보겠습니다", "결론적으로",
  "이 글에서는" 같은 전형적인 AI/블로그 클리셰 문구는 절대 쓰지 않습니다.
- 사진을 넣을 자리를 [사진: 설명] 형식으로 표시합니다. 그중 한 곳은
  홍어를 삭히는 옹기(항아리)나 손질 과정처럼 원재료·과정이 선명하게 드러나는
  장면을, 다른 한 곳은 완성된 메뉴가 먹음직스럽게 보이는 장면을 지정합니다.
  모두 홍어가 화면에 뚜렷하게 잘 보이는 구도로 씁니다.
- 가게 이름이나 대표 메뉴는 글 끝에서만 언급하지 말고, 중반쯤 한 번,
  마지막에서 한 번 — 최소 두 번 자연스럽게 언급합니다.
- 모바일 줄바꿈 기준: 한 단위(발화 또는 문단)가 길면 여러 줄로 나누되,
  글자 수를 억지로 맞추지 않고 의미가 자연스럽게 끊기는 곳에서만 줄을
  바꿉니다 — 하나의 의미·조사가 끝난 곳, 시간·상황 표현이 끝난 곳, 설명에서
  결과로 넘어가는 곳, 중요한 내용을 강조하기 직전. 형용사+명사, 부사+동사,
  음식명, 가게명, 고유명사는 절대 쪼개지 않습니다.
"""

SYSTEM_PROMPTS = {
    "expert": _COMMON_HEADER + """
가장 중요한 목표:
읽는 사람이 끝까지 쭉 읽게 되면서, 다 읽고 나면 홍어에 대해 하나라도
새로 알게 되는 글이어야 합니다.

출력 형식(반드시 그대로 지킵니다):
1번째 줄: "제목: <블로그 글 제목>" — 검색에 잘 걸리고 클릭하고 싶어지는 제목.
          제목에는 이모지를 쓰지 않습니다.
2번째 줄: 빈 줄
그 다음부터: 본문
맨 마지막 줄: "태그: #키워드1 #키워드2 ..." 형식으로 태그 6~8개.

글의 흐름:
1) 사람들이 실제로 궁금해하거나 오해하는 지점을 짚으며 시작
2) 핵심 답을 먼저 명확히 제시
3) 왜 그런지 근거를 풀어서 설명 (역사적 배경이나 원리)
4) 전문가만 아는 실용 정보 — 고르는 법, 구분법, 먹는 요령 중 하나
5) 가게에서 이 부분을 어떻게 하고 있는지 + 부담 없는 초대

분량·형식:
- 짧은 문단(2~4줄)으로 끊어 씁니다. 문단 사이는 빈 줄.
- [사진: 설명] 자리를 3곳 표시합니다.
- 분량은 공백 포함 900~1200자.
""" + _COMMON_RULES,

    "qna": _COMMON_HEADER + """
출력 형식(반드시 그대로 지킵니다):
1번째 줄: "제목: <블로그 글 제목>" — 검색에 잘 걸리고 클릭하고 싶어지는 제목.
          제목에는 이모지를 쓰지 않습니다.
2번째 줄: 빈 줄
그 다음부터: 사람들이 실제로 검색할 법한 질문과 사장님의 답변을 짧은
          인터뷰 형식으로 씁니다. 질문은 "Q. "로, 답변은 "A. "로 시작하고,
          질문-답변 쌍 사이는 빈 줄로 구분합니다. 질문은 2~3개, 답변마다
          정보를 하나씩 명확하게 전달합니다.
          [사진: 설명] 자리를 최소 2곳 표시합니다.
- 분량은 공백 포함 400~600자로 짧고 간결하게 씁니다.
""" + _COMMON_RULES,

    "column": _COMMON_HEADER + """
출력 형식(반드시 그대로 지킵니다):
1번째 줄: "제목: <블로그 글 제목>" — 검색에 잘 걸리고 클릭하고 싶어지는 제목.
          제목에는 이모지를 쓰지 않습니다.
2번째 줄: 빈 줄
그 다음부터: 질문-답변 형식 없이, 짧은 문단(2~4줄) 여러 개가 이어지는
          칼럼 형태로 씁니다. 순서는 궁금증을 유발하는 한 줄 훅 →
          정보·역사 한 문단 → 감각적인 맛 묘사 한 문단 → 가게 연결 →
          부담 없는 방문 권유. 문단과 문단 사이는 빈 줄로 구분합니다.
          [사진: 설명] 자리를 최소 2곳 표시합니다.
- 분량은 공백 포함 400~600자로 짧고 간결하게 씁니다.
""" + _COMMON_RULES,
}


def build_user_prompt(context: dict, condition: str | None = None) -> str:
    weather = context["weather"]
    if weather.get("available") and weather.get("temperature") is not None:
        weather_line = f"오늘 날씨: {weather['condition']}, 기온 약 {weather['temperature']}도"
    else:
        weather_line = f"오늘 날씨: {weather['condition']}"

    holiday_line = f"\n오늘은 '{context['holiday']}'입니다. 자연스럽게 언급해도 좋습니다." if context.get("holiday") else ""

    menu_str = ", ".join(SHOP_INFO["menu"])

    # 사장님이 직접 적은 조건. 사실 원칙을 덮어쓰지 못하도록 '요청'으로만 전달한다.
    condition_block = ""
    if condition and condition.strip():
        condition_block = f"""

이번 글에 대한 사장님의 추가 요청:
---
{condition.strip()}
---
위 요청은 글의 내용·강조점·길이에 대한 것으로만 반영합니다.
요청 내용이 앞의 사실 원칙(지어내지 않기)과 충돌하면 사실 원칙을 우선합니다."""

    return f"""오늘 정보:
- 날짜: {context['date']} ({context['season']})
- {weather_line}{holiday_line}
- 오늘 글의 키워드/주제: '{context['keyword']}' — 이 단어를 자연스럽게 최소 한 번 넣어주세요.

가게 정보:
- 상호: {SHOP_INFO['name']}
- 대표 메뉴: {menu_str}{condition_block}

위 정보를 반영해서 블로그 글 초안을 한 편 써주세요."""


def build_revision_prompt(context: dict, previous: dict, feedback: str,
                          condition: str | None = None) -> str:
    """이전 초안을 통째로 새로 쓰지 않고, 피드백이 가리키는 부분만 고치게 한다."""
    base = build_user_prompt(context, condition=condition)
    previous_text = f"제목: {previous.get('title', '')}\n\n{previous.get('body', '')}"

    return f"""{base}

아래는 방금 만든 초안입니다.

--- 이전 초안 시작 ---
{previous_text}
--- 이전 초안 끝 ---

사장님이 남긴 수정 요청:
---
{feedback.strip()}
---

이전 초안을 처음부터 새로 쓰지 말고, 위 수정 요청이 가리키는 부분만
고쳐서 전체 글을 다시 출력해 주세요. 요청과 무관한 문단은 표현을 바꾸지 말고
그대로 유지합니다. 출력 형식(제목 줄 + 본문)은 동일하게 지킵니다."""


def parse_output(raw: str) -> dict:
    """"제목: ..." 첫 줄 + 본문 + (있으면) "태그: ..." 마지막 줄을 나눈다."""
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

    # 마지막 줄이 "태그: ..."이면 본문에서 떼어내 따로 돌려준다.
    tags = ""
    lines = body.rstrip().split("\n")
    if lines and lines[-1].strip().startswith("태그:"):
        tags = lines[-1].strip()[len("태그:"):].strip()
        body = "\n".join(lines[:-1]).rstrip()

    return {"title": title, "body": body, "tags": tags}


def _call_model(prompt: str, concept: str) -> dict:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPTS[concept],
        max_output_tokens=MAX_OUTPUT_TOKENS[concept],
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


def generate_draft(context: dict, concept: str = DEFAULT_CONCEPT,
                   condition: str | None = None) -> dict:
    if concept not in CONCEPTS:
        concept = DEFAULT_CONCEPT
    return _call_model(build_user_prompt(context, condition=condition), concept)


def revise_draft(context: dict, previous: dict, feedback: str,
                 concept: str = DEFAULT_CONCEPT, condition: str | None = None) -> dict:
    if concept not in CONCEPTS:
        concept = DEFAULT_CONCEPT
    prompt = build_revision_prompt(context, previous, feedback, condition=condition)
    return _call_model(prompt, concept)
