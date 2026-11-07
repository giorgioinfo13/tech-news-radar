"""Operator commands for owner linking, reader approval, revocation, and deletion."""

import argparse
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.db import create_database_engine
from app.models import LOCAL_OWNER_ID, AppUser, ReaderInvitation


def link_owner(session: Session, subject: UUID) -> UUID:
    owner = session.get(AppUser, LOCAL_OWNER_ID)
    if owner is None or owner.role != "admin":
        raise ValueError("The reserved administrator profile is missing")
    if owner.supabase_subject == subject:
        return owner.id
    if owner.supabase_subject is not None:
        raise ValueError("The owner is already linked to another identity")
    result = session.execute(
        update(AppUser)
        .where(AppUser.id == LOCAL_OWNER_ID, AppUser.supabase_subject.is_(None))
        .values(supabase_subject=subject)
    )
    if result.rowcount != 1:
        raise ValueError("The owner link changed concurrently")
    return LOCAL_OWNER_ID


def invite_reader(session: Session, subject: UUID, name: str) -> UUID:
    name = name.strip()
    if not 1 <= len(name) <= 120:
        raise ValueError("Display name must contain 1 to 120 characters")
    existing = session.scalar(select(AppUser).where(AppUser.supabase_subject == subject))
    if existing is not None:
        if existing.role != "reader":
            raise ValueError("This identity belongs to an administrator")
        # Repeated invitations do not undo revocation or replace personal data.
        return existing.id
    user = AppUser(supabase_subject=subject, display_name=name, role="reader", active=True)
    session.add(user)
    session.flush()
    return user.id


def set_access(session: Session, subject: UUID, *, active: bool) -> UUID:
    user = session.scalar(select(AppUser).where(AppUser.supabase_subject == subject))
    if user is None:
        raise ValueError("This identity has no application profile")
    user.active = active
    return user.id


def delete_reader(session: Session, subject: UUID) -> UUID:
    user = session.scalar(
        select(AppUser).where(AppUser.supabase_subject == subject).with_for_update()
    )
    if user is None or user.role != "reader" or user.active or user.id == LOCAL_OWNER_ID:
        raise ValueError("Deletion requires an existing, revoked reader")
    user_id = user.id
    session.execute(delete(ReaderInvitation).where(ReaderInvitation.accepted_subject == subject))
    session.delete(user)
    session.flush()
    return user_id


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Explicitly approve or revoke application access")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("link-owner", "invite", "revoke", "activate", "delete-reader"):
        command = commands.add_parser(name)
        command.add_argument(
            "--subject", type=UUID, required=True, help="Verified Supabase user UUID"
        )
        if name == "invite":
            command.add_argument("--name", required=True)
        if name == "delete-reader":
            command.add_argument("--confirm-subject", type=UUID, required=True)
    args = parser.parse_args(argv)
    engine = None
    try:
        settings = Settings()
        if settings.supabase_url is None:
            raise ValueError("Configure TNR_SUPABASE_URL before provisioning identities")
        engine = create_database_engine(settings.migration_database_url or settings.database_url)
        with Session(engine) as session, session.begin():
            if args.command == "link-owner":
                user_id = link_owner(session, args.subject)
            elif args.command == "invite":
                user_id = invite_reader(session, args.subject, args.name)
            elif args.command == "delete-reader":
                if args.subject != args.confirm_subject:
                    raise ValueError("Identity confirmation does not match")
                user_id = delete_reader(session, args.subject)
            else:
                user_id = set_access(session, args.subject, active=args.command == "activate")
        print(f"Access operation completed for application user {user_id}")
        return 0
    except (ValueError, SQLAlchemyError):
        # Driver errors and configuration validation can contain credentials.
        print("Access operation failed. Check configuration, migrations, and identity conflicts.")
        return 1
    finally:
        if engine is not None:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
