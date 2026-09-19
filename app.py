"""화면 + 버튼. 사장님이 보는 부분(4단계).

보안 원칙(기획서 6절): 모든 외부 API 호출은 여기(서버)에서만 처리하고,
브라우저에는 키를 절대 내려보내지 않는다. 오류는 내부 정보 없이
일반 메시지만 보여준다. 버튼 연타 방지 + 일일 호출 횟수 제한을 둔다.
"""

import logging
import time
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from collector import collect_context, list_suggested_keywords
from generator import CONCEPTS, DEFAULT_CONCEPT
from quality import generate_with_quality_gate, revise_with_quality_check

load_dotenv()

logger = logging.getLogger("uvicorn.error")

app = FastAPI(title="묵동홍어마을 블로그 글 생성기")
templates = Jinja2Templates(directory="templates")

MIN_INTERVAL_SEC = 5  # 버튼 연타 방지
DAILY_LIMIT = 50  # 비용 보호 장치
KEYWORD_MAX_LENGTH = 60
CONDITION_MAX_LENGTH = 500
FEEDBACK_MAX_LENGTH = 500
DRAFT_MAX_LENGTH = 5000


class GenerateRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=KEYWORD_MAX_LENGTH)
    concept: str | None = None
    condition: str | None = Field(default=None, max_length=CONDITION_MAX_LENGTH)


class ReviseRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=KEYWORD_MAX_LENGTH)
    concept: str | None = None
    condition: str | None = Field(default=None, max_length=CONDITION_MAX_LENGTH)
    feedback: str = Field(min_length=1, max_length=FEEDBACK_MAX_LENGTH)
    previous_title: str = Field(default="", max_length=DRAFT_MAX_LENGTH)
    previous_body: str = Field(default="", max_length=DRAFT_MAX_LENGTH)


_last_call_at = 0.0
_daily_count = {"date": None, "count": 0}


def _check_rate_limits() -> None:
    """연타 방지 + 하루 호출 상한. 생성과 수정 모두 같은 한도를 쓴다."""
    global _last_call_at

    now = time.time()
    if now - _last_call_at < MIN_INTERVAL_SEC:
        raise HTTPException(status_code=429, detail="너무 빨리 눌렀어요. 잠시 후 다시 시도해 주세요.")

    today = date.today().isoformat()
    if _daily_count["date"] != today:
        _daily_count["date"] = today
        _daily_count["count"] = 0
    if _daily_count["count"] >= DAILY_LIMIT:
        raise HTTPException(status_code=429, detail="오늘의 생성 횟수를 모두 사용했습니다. 내일 다시 시도해 주세요.")

    _last_call_at = now
    _daily_count["count"] += 1


def _response(result: dict, context: dict, concept: str) -> dict:
    return {
        "title": result["title"],
        "body": result["body"],
        "tags": result.get("tags", ""),
        "passed": result["passed"],
        "keyword": context["keyword"],
        "concept": concept,
    }


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/api/keywords")
def keywords():
    """키워드 입력칸 아래 추천 칩에 쓸 목록. 생성 비용이 안 드는 조회라
    연타 방지·일일 제한을 적용하지 않는다."""
    return list_suggested_keywords()


@app.post("/api/generate")
def generate(body: GenerateRequest):
    _check_rate_limits()
    concept = body.concept if body.concept in CONCEPTS else DEFAULT_CONCEPT

    try:
        context = collect_context(keyword=body.keyword)
        result = generate_with_quality_gate(context, concept=concept, condition=body.condition)
    except Exception:
        logger.exception("글 생성 실패")  # 사용자에겐 안 보이고 서버 로그에만 남음
        raise HTTPException(status_code=500, detail="글을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")

    return _response(result, context, concept)


@app.post("/api/revise")
def revise(body: ReviseRequest):
    _check_rate_limits()
    concept = body.concept if body.concept in CONCEPTS else DEFAULT_CONCEPT

    try:
        context = collect_context(keyword=body.keyword)
        previous = {"title": body.previous_title, "body": body.previous_body}
        result = revise_with_quality_check(
            context, previous, body.feedback, concept=concept, condition=body.condition
        )
    except Exception:
        logger.exception("글 수정 실패")
        raise HTTPException(status_code=500, detail="글을 고치는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")

    return _response(result, context, concept)
