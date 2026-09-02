"""3단계: 품질 검사 + 미달 시 재생성. 이 서비스의 핵심 차별점(기획서 3절).

AI 티·키워드 포함·사진자리·가게정보를 자동 점검하고, 미달이면
QUALITY_MAX_REGEN_ATTEMPTS 만큼 다시 쓴다.
"""

from config import QUALITY_MAX_REGEN_ATTEMPTS, QUALITY_MIN_LENGTH, SHOP_INFO
from generator import generate_draft

AI_TELL_PHRASES = [
    "안녕하세요! 오늘은", "포스팅을 시작하겠습니다", "함께 알아보겠습니다",
    "결론적으로", "요약하자면", "이 글에서는", "정리해보면", "이상으로",
    "다음과 같습니다", "포스팅을 마치겠습니다", "제가 도와드리겠습니다",
]


def check_quality(text: str, context: dict) -> dict:
    reasons = []

    if len(text) < QUALITY_MIN_LENGTH:
        reasons.append(f"분량 부족 ({len(text)}자 < {QUALITY_MIN_LENGTH}자)")

    if SHOP_INFO["name"] not in text:
        reasons.append("가게 이름 미포함")

    if context["keyword"] not in text:
        reasons.append(f"키워드 미포함 ('{context['keyword']}')")

    if "[사진" not in text:
        reasons.append("사진자리 표시 없음")

    if "?" not in text:
        reasons.append("손주 질문(Q&A 형식) 흔적 없음")

    found_tells = [p for p in AI_TELL_PHRASES if p in text]
    if found_tells:
        reasons.append(f"AI 흔적 표현 감지: {', '.join(found_tells)}")

    return {"passed": len(reasons) == 0, "reasons": reasons}


def generate_with_quality_gate(context: dict) -> dict:
    attempts = []
    for _ in range(QUALITY_MAX_REGEN_ATTEMPTS + 1):
        draft = generate_draft(context)
        result = check_quality(draft, context)
        attempts.append({"draft": draft, "result": result})
        if result["passed"]:
            break

    best = attempts[-1]
    return {
        "draft": best["draft"],
        "passed": best["result"]["passed"],
        "reasons": best["result"]["reasons"],
        "attempt_count": len(attempts),
    }
