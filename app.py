"""화면 + 버튼. 사장님이 보는 부분(4단계).

보안 원칙(기획서 6절): 모든 외부 API 호출은 여기(서버)에서만 처리하고,
브라우저에는 키를 절대 내려보내지 않는다. 오류는 내부 정보 없이
일반 메시지만 보여준다. 버튼 연타 방지 + 일일 호출 횟수 제한을 둔다.
"""

import time
from datetime import date

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from collector import collect_context
from quality import generate_with_quality_gate

load_dotenv()

app = FastAPI(title="묵동홍어마을 블로그 글 생성기")
templates = Jinja2Templates(directory="templates")

MIN_INTERVAL_SEC = 5  # 버튼 연타 방지
DAILY_LIMIT = 50  # 비용 보호 장치
KEYWORD_MAX_LENGTH = 60


class GenerateRequest(BaseModel):
    keyword: str | None = Field(default=None, max_length=KEYWORD_MAX_LENGTH)

_last_call_at = 0.0
_daily_count = {"date": None, "count": 0}


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.post("/api/generate")
def generate(body: GenerateRequest):
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

    try:
        context = collect_context(keyword=body.keyword)
        result = generate_with_quality_gate(context)
    except Exception:
        raise HTTPException(status_code=500, detail="글을 만드는 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.")

    return {
        "title": result["title"],
        "body": result["body"],
        "passed": result["passed"],
        "keyword": context["keyword"],
    }
