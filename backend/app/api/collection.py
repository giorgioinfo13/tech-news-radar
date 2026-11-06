"""Operator-only collection trigger, independent of user identity tokens."""

import logging
from secrets import compare_digest

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.dependencies import reject_refresh
from app.collection.scheduler import ScanResult
from app.collection.service import RefreshRejected

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/internal/collect", response_model=ScanResult, include_in_schema=False)
def collect_due_sources(request: Request, response: Response) -> ScanResult:
    headers = {"Cache-Control": "no-store"}
    secret = request.app.state.settings.collection_trigger_secret
    if secret is None:
        raise HTTPException(404, "Not found", headers=headers)
    values = request.headers.getlist("authorization")
    scheme, _, supplied = values[0].partition(" ") if len(values) == 1 else ("", "", "")
    if scheme.lower() != "bearer" or not compare_digest(
        supplied.encode("utf-8"), secret.get_secret_value().encode("ascii")
    ):
        raise HTTPException(401, "Invalid collection credential", headers=headers)
    response.headers.update(headers)
    try:
        return request.app.state.collection_trigger.run()
    except RefreshRejected as exc:
        error = reject_refresh(exc)
        error.headers = {**(error.headers or {}), **headers}
        raise error from exc
    except Exception as exc:
        logger.error("External collection scan failed (%s)", type(exc).__name__)
        raise HTTPException(503, "Collection scan failed", headers=headers) from None
