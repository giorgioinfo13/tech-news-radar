"""Moderated source requests. Pending proposals never enter the collector."""

from hashlib import sha256
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.api.dependencies import (
    AdminDep,
    CollectorDep,
    PaginationDep,
    ResourceId,
    SessionDep,
    UserDep,
    commit_or_conflict,
    get_or_404,
    paginate,
    source_write_guard,
)
from app.collection.download import FeedError, checked_url
from app.collection.parsing import parse_feed
from app.db import insert_once, lock_access_decisions, utc_now
from app.models import AppUser, Category, Source, SourceProposal, Subscription
from app.schemas import Page, ProposalApprove, ProposalCreate, ProposalRead, ProposalReject

router = APIRouter(prefix="/proposals", tags=["proposals"])
MAX_PENDING = 5


def write_transaction(session: Session) -> None:
    # Discard authorization/preflight read snapshots before acquiring the write gate.
    session.rollback()
    lock_access_decisions(session)


def active_user(session: Session, user_id, *, admin=False) -> AppUser:
    user = session.get(AppUser, user_id, populate_existing=True)
    if user is None or not user.active or (admin and user.role != "admin"):
        raise HTTPException(403, "User is not authorized")
    return user


def pending(proposal: SourceProposal) -> None:
    if proposal.status != "pending":
        raise HTTPException(409, "The proposal is no longer pending")


@router.get("", response_model=Page[ProposalRead])
def list_proposals(
    user: UserDep,
    session: SessionDep,
    pagination: PaginationDep,
    status: Literal["pending", "approved", "rejected", "cancelled"] | None = None,
):
    statement = select(SourceProposal).options(joinedload(SourceProposal.user))
    if user.role != "admin":
        statement = statement.where(SourceProposal.user_id == user.id)
    if status:
        statement = statement.where(SourceProposal.status == status)
    return paginate(
        session,
        statement.order_by(SourceProposal.created_at.desc(), SourceProposal.id.desc()),
        pagination,
    )


@router.post("", response_model=ProposalRead, status_code=201)
def create_proposal(data: ProposalCreate, user: UserDep, session: SessionDep):
    if data.url:
        try:
            checked_url(data.url)  # Syntax only: no DNS, download or discovery.
        except FeedError as exc:
            raise HTTPException(422, str(exc)) from exc
    user_id = user.id
    write_transaction(session)
    active_user(session, user_id)
    count = session.scalar(
        select(func.count())
        .select_from(SourceProposal)
        .where(SourceProposal.user_id == user_id, SourceProposal.status == "pending")
    )
    if count >= MAX_PENDING:
        raise HTTPException(409, "At most five pending proposals are allowed")
    if data.category_id is not None:
        get_or_404(session, Category, data.category_id)
    proposal = SourceProposal(
        **data.model_dump(),
        user_id=user_id,
        name_key=sha256(data.name.casefold().encode()).hexdigest(),
    )
    session.add(proposal)
    commit_or_conflict(session, "A pending proposal with this name already exists")
    return proposal


@router.post("/{proposal_id}/cancel", response_model=ProposalRead)
def cancel_proposal(proposal_id: ResourceId, user: UserDep, session: SessionDep):
    user_id = user.id
    write_transaction(session)
    active_user(session, user_id)
    proposal = get_or_404(session, SourceProposal, proposal_id)
    if proposal.user_id != user_id:
        raise HTTPException(404, "SourceProposal not found")
    if proposal.status == "cancelled":
        return proposal
    pending(proposal)
    proposal.status, proposal.decided_at, proposal.decided_by = "cancelled", utc_now(), user_id
    session.commit()
    return proposal


@router.post("/{proposal_id}/reject", response_model=ProposalRead)
def reject_proposal(
    proposal_id: ResourceId, data: ProposalReject, admin: AdminDep, session: SessionDep
):
    admin_id = admin.id
    write_transaction(session)
    active_user(session, admin_id, admin=True)
    proposal = get_or_404(session, SourceProposal, proposal_id)
    if proposal.status == "rejected" and proposal.reason == data.reason:
        return proposal
    pending(proposal)
    proposal.status, proposal.decided_at, proposal.decided_by = "rejected", utc_now(), admin_id
    proposal.reason = data.reason
    session.commit()
    return proposal


@router.post(
    "/{proposal_id}/approve",
    response_model=ProposalRead,
    dependencies=[Depends(source_write_guard)],
)
def approve_proposal(
    proposal_id: ResourceId,
    data: ProposalApprove,
    admin: AdminDep,
    session: SessionDep,
    collector: CollectorDep,
):
    admin_id = admin.id
    proposal = get_or_404(session, SourceProposal, proposal_id)
    if proposal.status == "approved":
        return proposal
    pending(proposal)
    # Link an existing exact URL automatically; never change its settings.
    source_id = data.source_id
    if source_id is None:
        source_id = session.scalar(select(Source.id).where(Source.feed_url == data.feed_url))
    session.rollback()
    if source_id is None:
        try:
            download = collector.downloader.fetch(data.feed_url)
            parse_feed(download.body, download.url, collector.settings.feed_max_entries)
        except FeedError as exc:
            raise HTTPException(422, "The RSS/Atom feed could not be validated") from exc
    # HTTP finished. Re-read every mutable condition inside a short atomic write.
    write_transaction(session)
    active_user(session, admin_id, admin=True)
    proposal = get_or_404(session, SourceProposal, proposal_id)
    if proposal.status == "approved":
        return proposal
    pending(proposal)
    proposer = session.get(AppUser, proposal.user_id, populate_existing=True)
    if proposer is None or not proposer.active:
        raise HTTPException(409, "The proposer no longer has access; reject the proposal instead")
    if source_id is not None:
        source = get_or_404(session, Source, source_id)
    else:
        # A source may have been added while the network request was running.
        source = session.scalar(select(Source).where(Source.feed_url == data.feed_url))
        if source is None:
            if data.category_id is not None:
                get_or_404(session, Category, data.category_id)
            source = Source(name=data.name, feed_url=data.feed_url, category_id=data.category_id)
            session.add(source)
            try:
                session.flush()
            except IntegrityError as exc:
                session.rollback()
                raise HTTPException(
                    409, "The source or category changed; reload before trying again"
                ) from exc
    proposal.status, proposal.decided_at, proposal.decided_by = "approved", utc_now(), admin_id
    proposal.source_id = source.id
    proposal.approved_name, proposal.approved_feed_url = source.name, source.feed_url
    if proposal.follow_on_approval:
        insert_once(session, Subscription, {"user_id": proposal.user_id, "source_id": source.id})
    commit_or_conflict(session, "The source or category changed; reload before trying again")
    return proposal
