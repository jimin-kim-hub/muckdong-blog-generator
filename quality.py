"""3단계: 품질 검사 + 미달 시 재생성. 이 서비스의 핵심 차별점(기획서 3절).

AI 티·키워드 포함·사진자리·가게정보·제목을 자동 점검하고,
미달이면 QUALITY_MAX_REGEN_ATTEMPTS 만큼 다시 쓴다.
컨셉별로 추가 항목을 본다(qna는 Q./A., expert는 태그·분량).

피드백 재작성(revise)은 사장님이 이미 확인한 초안을 고치는 것이라
재생성 루프를 돌리지 않고 검사 결과만 붙여서 돌려준다.
"""

from config import QUALITY_MAX_REGEN_ATTEMPTS, QUALITY_MIN_LENGTH, SHOP_INFO
from generator import DEFAULT_CONCEPT, generate_draft, revise_draft

AI_TELL_PHRASES = [
    "안녕하세요! 오늘은", "포스팅을 시작하겠습니다", "함께 알아보겠습니다",
    "결론적으로", "요약하자면", "이 글에서는", "정리해보면", "이상으로",
    "다음과 같습니다", "포스팅을 마치겠습니다", "제가 도와드리겠습니다",
]

EXPERT_MIN_LENGTH = 700  # 정보형은 길게 쓰는 것이 목적이라 따로 본다


def check_quality(draft: dict, context: dict, concept: str = DEFAULT_CONCEPT) -> dict:
    title = draft["title"]
    body = draft["body"]
    reasons = []

    if not title:
        reasons.append("제목 누락")

    min_length = EXPERT_MIN_LENGTH if concept == "expert" else QUALITY_MIN_LENGTH
    if len(body) < min_length:
        reasons.append(f"분량 부족 ({len(body)}자 < {min_length}자)")

    if SHOP_INFO["name"] not in body:
        reasons.append("가게 이름 미포함")

    if context["keyword"] not in body and context["keyword"] not in title:
        reasons.append(f"키워드 미포함 ('{context['keyword']}')")

    if "[사진" not in body:
        reasons.append("사진자리 표시 없음")

    if concept == "qna" and ("Q." not in body or "A." not in body):
        reasons.append("Q&A 형식(Q./A.) 표시 없음")

    if concept == "expert" and not draft.get("tags"):
        reasons.append("태그 누락")

    found_tells = [p for p in AI_TELL_PHRASES if p in body]
    if found_tells:
        reasons.append(f"AI 흔적 표현 감지: {', '.join(found_tells)}")

    return {"passed": len(reasons) == 0, "reasons": reasons}


def _as_result(draft: dict, result: dict, attempt_count: int) -> dict:
    return {
        "title": draft["title"],
        "body": draft["body"],
        "tags": draft.get("tags", ""),
        "passed": result["passed"],
        "reasons": result["reasons"],
        "attempt_count": attempt_count,
    }


def generate_with_quality_gate(context: dict, concept: str = DEFAULT_CONCEPT,
                               condition: str | None = None) -> dict:
    attempts = []
    for _ in range(QUALITY_MAX_REGEN_ATTEMPTS + 1):
        draft = generate_draft(context, concept=concept, condition=condition)
        result = check_quality(draft, context, concept=concept)
        attempts.append({"draft": draft, "result": result})
        if result["passed"]:
            break

    best = attempts[-1]
    return _as_result(best["draft"], best["result"], len(attempts))


def revise_with_quality_check(context: dict, previous: dict, feedback: str,
                              concept: str = DEFAULT_CONCEPT,
                              condition: str | None = None) -> dict:
    """피드백 반영은 한 번만 호출한다. 재생성 루프를 돌리면 사장님이 남긴
    수정 요청과 무관하게 글이 계속 바뀌어 확인이 처음부터 다시 필요해진다."""
    draft = revise_draft(context, previous, feedback, concept=concept, condition=condition)
    result = check_quality(draft, context, concept=concept)
    return _as_result(draft, result, 1)
