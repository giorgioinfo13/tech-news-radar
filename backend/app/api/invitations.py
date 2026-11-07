from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import delete, select

from app.api.dependencies import (
    AdminDep,
    PaginationDep,
    SessionDep,
    commit_or_conflict,
    paginate,
    require_admin,
)
from app.models import ReaderInvitation
from app.schemas import InvitationCreate, InvitationRead, Page

router = APIRouter(
    prefix="/invitations", tags=["invitations"], dependencies=[Depends(require_admin)]
)


@router.get("", response_model=Page[InvitationRead])
def list_invitations(session: SessionDep, pagination: PaginationDep):
    return paginate(
        session,
        select(ReaderInvitation).order_by(ReaderInvitation.created_at.desc(), ReaderInvitation.id),
        pagination,
    )


@router.post("", response_model=InvitationRead, status_code=201)
def create_invitation(
    data: InvitationCreate, admin: AdminDep, session: SessionDep, request: Request
):
    settings = request.app.state.settings
    if settings.supabase_url and not settings.supabase_publishable_key:
        raise HTTPException(status_code=503, detail="Invitation verification is not configured")
    invitation = ReaderInvitation(**data.model_dump(), invited_by=admin.id)
    session.add(invitation)
    commit_or_conflict(session, "An invitation for this email already exists")
    return invitation


@router.delete("/{invitation_id}", status_code=204)
def cancel_invitation(invitation_id: UUID, session: SessionDep) -> Response:
    result = session.execute(
        delete(ReaderInvitation).where(
            ReaderInvitation.id == invitation_id, ReaderInvitation.accepted_at.is_(None)
        )
    )
    if result.rowcount != 1:
        session.rollback()
        raise HTTPException(status_code=409, detail="Only pending invitations can be cancelled")
    session.commit()
    return Response(status_code=204)
