"""Admin-approved email invitations, claimed once by a verified Google identity."""

import json
import re
from threading import Lock
from time import monotonic
from uuid import UUID

import httpx
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import AuthenticationUnavailable
from app.db import utc_now
from app.models import AppUser, ReaderInvitation


def normalize_email(value: str) -> str:
    """Case-insensitive ASCII mailbox matching; never fold dots or plus aliases."""
    value = value.strip().lower()
    if len(value) > 254 or value.count("@") != 1:
        raise ValueError("Enter a valid email address")
    local, domain = value.split("@")
    if (
        not 1 <= len(local) <= 64
        or not re.fullmatch(
            r"[a-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-z0-9!#$%&'*+/=?^_`{|}~-]+)*", local
        )
        or "." not in domain
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in domain.split(".")
        )
    ):
        raise ValueError("Enter a valid ASCII email address")
    return value


class GoogleIdentityVerifier:
    def __init__(self, origin: str, publishable_key: str | None):
        self.url = f"{origin}/auth/v1/user"
        self.key = publishable_key
        self._lock = Lock()
        self._retry_at = 0.0

    def matches(self, token: str, subject: UUID, email: str) -> bool:
        # Only called for a pending invitation after cryptographic JWT verification.
        # No service-role key, caller-selected URL, redirects, or user_metadata trust.
        if not self.key:
            raise AuthenticationUnavailable
        if not self._lock.acquire(timeout=1):
            raise AuthenticationUnavailable
        try:
            if monotonic() < self._retry_at:
                raise AuthenticationUnavailable
            with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
                with client.stream(
                    "GET",
                    self.url,
                    headers={"Authorization": f"Bearer {token}", "apikey": self.key},
                ) as response:
                    if response.status_code in (401, 403):
                        return False
                    if response.status_code != 200:
                        raise AuthenticationUnavailable
                    payload = bytearray()
                    for chunk in response.iter_bytes(chunk_size=8192):
                        payload.extend(chunk)
                        if len(payload) > 65536:
                            raise AuthenticationUnavailable
            user = json.loads(payload)
            if (
                user.get("id") != str(subject)
                or not user.get("email_confirmed_at")
                or normalize_email(user.get("email", "")) != email
                or user.get("is_anonymous") is not False
            ):
                return False
            for identity in user.get("identities", []):
                data = identity.get("identity_data") or {}
                if (
                    identity.get("provider") == "google"
                    and identity.get("user_id") == str(subject)
                    and data.get("email_verified") is True
                    and normalize_email(data.get("email", "")) == email
                ):
                    return True
            return False
        except (httpx.HTTPError, AuthenticationUnavailable):
            self._retry_at = monotonic() + 10
            raise AuthenticationUnavailable from None
        except (ValueError, TypeError, AttributeError, RecursionError):
            return False
        finally:
            self._lock.release()


def claim_invitation(
    session: Session, subject: UUID, email: object, token: str, verifier: GoogleIdentityVerifier
) -> UUID | None:
    try:
        address = normalize_email(email) if isinstance(email, str) else None
    except ValueError:
        return None
    invitation = (
        session.scalar(
            select(ReaderInvitation).where(
                ReaderInvitation.email == address, ReaderInvitation.accepted_at.is_(None)
            )
        )
        if address
        else None
    )
    if invitation is None:
        return None
    invitation_id, name = invitation.id, invitation.display_name
    # Release the read transaction before the remote identity lookup.
    session.rollback()
    if not verifier.matches(token, subject, address):
        return None
    try:
        # Conditional write serializes both claim/claim and claim/cancel races.
        result = session.execute(
            update(ReaderInvitation)
            .where(ReaderInvitation.id == invitation_id, ReaderInvitation.accepted_at.is_(None))
            .values(accepted_at=utc_now(), accepted_subject=subject)
        )
        if result.rowcount != 1:
            session.rollback()
            return session.scalar(select(AppUser.id).where(AppUser.supabase_subject == subject))
        existing = session.scalar(select(AppUser).where(AppUser.supabase_subject == subject))
        if existing is not None:
            # A concurrent operator approval/revocation takes precedence, without changes.
            session.rollback()
            return existing.id
        user = AppUser(supabase_subject=subject, display_name=name, role="reader", active=True)
        session.add(user)
        session.flush()
        user_id = user.id
        session.commit()
        return user_id
    except IntegrityError:
        session.rollback()
        return session.scalar(select(AppUser.id).where(AppUser.supabase_subject == subject))
