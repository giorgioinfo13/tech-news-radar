"""Approved readers share results and project quota; reads never call Gemini."""

from asyncio import to_thread
from secrets import compare_digest

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.dependencies import SessionDep, UserDep

router = APIRouter(prefix="/briefs", tags=["briefs"])
internal_router = APIRouter(prefix="/briefs/internal")


@router.get("/digest")
async def read_digest(user: UserDep, session: SessionDep, request: Request):
    user_id = user.id
    session.rollback()
    state = await to_thread(request.app.state.briefs.read, None, user_id)
    return {**state, "can_generate": False}


@internal_router.post("/run", include_in_schema=False)
async def run_digest(request: Request, response: Response):
    headers = {"Cache-Control": "no-store"}
    settings = request.app.state.settings
    secret = settings.ai_digest_trigger_secret
    if not settings.ai_digest_enabled or secret is None:
        raise HTTPException(404, "Not found", headers=headers)
    values = request.headers.getlist("authorization")
    scheme, _, supplied = values[0].partition(" ") if len(values) == 1 else ("", "", "")
    if scheme.lower() != "bearer" or not compare_digest(
        supplied.encode("utf-8"), secret.get_secret_value().encode("ascii")
    ):
        raise HTTPException(401, "Invalid digest credential", headers=headers)
    response.headers.update(headers)
    state = await request.app.state.briefs.generate(None, None)
    # The automation never receives summaries, user data, or raw provider diagnostics.
    return {"code": state["code"], "attempts_remaining": state["attempts_remaining"]}
