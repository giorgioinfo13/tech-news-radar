from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import UUID, uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session
from test_auth import ORIGIN
from test_auth import signing as signing

from app.access import delete_reader, invite_reader, link_owner, set_access
from app.config import Settings
from app.invitations import claim_invitation, normalize_email
from app.main import create_app
from app.models import LOCAL_OWNER_ID, AppUser, ReaderInvitation, Subscription

EMAIL = "friend@example.org"


def google_user(subject, email=EMAIL):
    return {
        "id": str(subject),
        "email": email,
        "email_confirmed_at": "2026-01-01T00:00:00Z",
        "is_anonymous": False,
        "identities": [
            {
                "provider": "google",
                "user_id": str(subject),
                "identity_data": {"email": email, "email_verified": True},
            }
        ],
    }


@pytest.fixture
async def invited_app(database, signing, monkeypatch):
    owner = uuid4()
    with Session(database) as session, session.begin():
        link_owner(session, owner)
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            supabase_url=ORIGIN,
            supabase_publishable_key="sb_publishable_test",
            scheduler_enabled=False,
        )
    )
    state = {"payload": {}, "status": 200, "calls": 0, "callback": None}
    original = httpx.Client

    def handle(request):
        state["calls"] += 1
        assert str(request.url) == f"{ORIGIN}/auth/v1/user"
        assert request.headers["apikey"] == "sb_publishable_test"
        assert request.headers["authorization"].startswith("Bearer ")
        if state["callback"]:
            state["callback"]()
        return httpx.Response(state["status"], json=state["payload"])

    monkeypatch.setattr(
        httpx, "Client", lambda **kw: original(**kw, transport=httpx.MockTransport(handle))
    )
    token, _ = signing

    def headers(subject=owner, email=None, **extra):
        return {"Authorization": f"Bearer {token(subject, changes={'email': email, **extra})}"}

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client, headers, state, app


@pytest.mark.anyio
async def test_admin_invites_normalizes_paginates_and_cancels(database, invited_app):
    client, headers, state, _ = invited_app
    data = {"email": " Friend@Example.ORG ", "display_name": " Friend "}
    response = await client.post("/api/invitations", headers=headers(), json=data)
    assert response.status_code == 201
    invitation = response.json()
    assert invitation["email"] == EMAIL
    assert invitation["display_name"] == "Friend"
    assert invitation["accepted_at"] is None
    assert "accepted_subject" not in invitation and "invited_by" not in invitation
    assert (await client.post("/api/invitations", headers=headers(), json=data)).status_code == 409
    page = (await client.get("/api/invitations?limit=1&offset=1", headers=headers())).json()
    assert page["total"] == 1 and page["items"] == []
    with Session(database) as session:
        assert session.scalar(select(ReaderInvitation)).invited_by == LOCAL_OWNER_ID
        assert session.scalar(select(func.count()).select_from(AppUser)) == 1
    path = f"/api/invitations/{invitation['id']}"
    assert (await client.delete(path, headers=headers())).status_code == 204
    assert (await client.delete(path, headers=headers())).status_code == 409
    assert state["calls"] == 0


@pytest.mark.anyio
async def test_claim_is_reader_only_and_revocation_and_deletion_cannot_be_undone(
    database,
    invited_app,
):
    client, headers, state, _ = invited_app
    subject = uuid4()
    state["payload"] = google_user(subject)
    pending = (
        await client.post(
            "/api/invitations",
            headers=headers(),
            json={
                "email": EMAIL,
                "display_name": "Friend",
            },
        )
    ).json()
    reader_headers = headers(subject, EMAIL, user_metadata={"role": "admin"})
    result = await client.get("/api/me", headers=reader_headers)
    assert result.status_code == 200
    assert result.json()["role"] == "reader" and result.json()["display_name"] == "Friend"
    assert result.json()["id"] != str(LOCAL_OWNER_ID)
    assert (await client.get("/api/subscriptions", headers=reader_headers)).json()["total"] == 0
    assert (await client.get("/api/me", headers=reader_headers)).status_code == 200
    assert state["calls"] == 1  # Approved users do not depend on the Auth user endpoint.
    for method, path, data in [
        ("GET", "/api/invitations", None),
        ("POST", "/api/invitations", {"email": "other@example.org", "display_name": "Other"}),
        ("DELETE", f"/api/invitations/{pending['id']}", None),
    ]:
        assert (
            await client.request(method, path, headers=reader_headers, json=data)
        ).status_code == 403
        assert (await client.request(method, path, json=data)).status_code == 401
    assert (
        await client.delete(f"/api/invitations/{pending['id']}", headers=headers())
    ).status_code == 409
    with Session(database) as session, session.begin():
        owner = session.get(AppUser, LOCAL_OWNER_ID)
        assert owner.role == "admin" and owner.active
        assert session.scalar(select(func.count()).select_from(Subscription)) == 0
        set_access(session, subject, active=False)
    assert (await client.get("/api/me", headers=reader_headers)).status_code == 403
    with Session(database) as session, session.begin():
        session.execute(delete(AppUser).where(AppUser.supabase_subject == subject))
    assert (await client.get("/api/me", headers=reader_headers)).status_code == 403
    assert state["calls"] == 1


@pytest.mark.anyio
@pytest.mark.parametrize(
    "failure",
    [
        "unknown_email",
        "missing_email",
        "wrong_subject",
        "unconfirmed",
        "anonymous",
        "wrong_provider",
        "wrong_identity_email",
        "unverified",
        "metadata_only",
        "wrong_user_id",
        "malformed",
        "cancelled_during_lookup",
        "upstream",
        "redirect",
        "missing_key",
    ],
)
async def test_untrusted_or_unavailable_identity_never_consumes_invite(
    database,
    invited_app,
    failure,
):
    client, headers, state, app = invited_app
    subject = uuid4()
    state["payload"] = payload = google_user(subject)
    pending = (
        await client.post(
            "/api/invitations",
            headers=headers(),
            json={
                "email": EMAIL,
                "display_name": "Friend",
            },
        )
    ).json()
    email = EMAIL
    if failure == "unknown_email":
        email = "stranger@example.org"
    elif failure == "missing_email":
        email = None
    elif failure == "wrong_subject":
        payload["id"] = str(uuid4())
    elif failure == "unconfirmed":
        payload["email_confirmed_at"] = None
    elif failure == "anonymous":
        payload["is_anonymous"] = True
    elif failure == "wrong_provider":
        payload["identities"][0]["provider"] = "email"
    elif failure == "wrong_identity_email":
        payload["identities"][0]["identity_data"]["email"] = "other@example.org"
    elif failure == "unverified":
        payload["identities"][0]["identity_data"]["email_verified"] = "true"
    elif failure == "wrong_user_id":
        payload["identities"][0]["user_id"] = str(uuid4())
    elif failure == "metadata_only":
        payload["identities"] = []
        payload["user_metadata"] = {"email": EMAIL, "email_verified": True, "provider": "google"}
    elif failure == "malformed":
        state["payload"] = []
    elif failure == "upstream":
        state["status"] = 503
    elif failure == "redirect":
        state["status"] = 302
    elif failure == "missing_key":
        app.state.google_identity_verifier.key = None
    elif failure == "cancelled_during_lookup":

        def cancel():
            with Session(database) as session, session.begin():
                session.execute(delete(ReaderInvitation))

        state["callback"] = cancel
    expected = 503 if failure in {"upstream", "redirect", "missing_key"} else 403
    response = await client.get("/api/me", headers=headers(subject, email))
    assert response.status_code == expected
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 1
        saved = session.get(ReaderInvitation, UUID(pending["id"]))
        assert saved is None or saved.accepted_at is None
    if expected == 503:
        assert response.headers["Retry-After"] == "10"
        assert (await client.get("/api/me", headers=headers(subject, email))).status_code == 503
        assert state["calls"] <= 1  # Backoff prevents repeated upstream requests.


@pytest.mark.anyio
@pytest.mark.parametrize(
    "data",
    [
        {"email": "invalid", "display_name": "Friend"},
        {"email": EMAIL, "display_name": " "},
        {"email": EMAIL, "display_name": "Friend", "role": "admin"},
        {"email": EMAIL, "display_name": "Friend", "accepted_subject": str(uuid4())},
    ],
)
async def test_invite_rejects_invalid_or_privileged_fields(invited_app, data):
    client, headers, _, _ = invited_app
    assert (await client.post("/api/invitations", headers=headers(), json=data)).status_code == 422


def test_concurrent_claims_create_one_profile(database):
    subject = uuid4()
    with Session(database) as session, session.begin():
        session.add(ReaderInvitation(email=EMAIL, display_name="Friend", invited_by=LOCAL_OWNER_ID))
    barrier = Barrier(2)

    class Verifier:
        def matches(self, *args):
            barrier.wait(timeout=10)
            return True

    def claim(_):
        with Session(database) as session:
            return claim_invitation(session, subject, EMAIL, "test-token", Verifier())

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, range(2)))
    assert results[0] is not None and results[0] == results[1]
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 2


def test_email_aliases_are_not_folded_and_secret_keys_are_rejected():
    assert normalize_email(" Friend.Name+News@Example.org ") == "friend.name+news@example.org"
    for key in ("sb_secret_private", "legacy-jwt"):
        with pytest.raises(ValidationError):
            Settings(_env_file=None, supabase_publishable_key=key)


@pytest.mark.anyio
async def test_pending_invite_does_not_reactivate_an_existing_revoked_reader(database, invited_app):
    client, headers, state, _ = invited_app
    subject = uuid4()
    with Session(database) as session, session.begin():
        invite_reader(session, subject, "Existing")
        set_access(session, subject, active=False)
    assert (
        await client.post(
            "/api/invitations",
            headers=headers(),
            json={
                "email": EMAIL,
                "display_name": "Replacement",
            },
        )
    ).status_code == 201
    assert (await client.get("/api/me", headers=headers(subject, EMAIL))).status_code == 403
    with Session(database) as session:
        reader = session.scalar(select(AppUser).where(AppUser.supabase_subject == subject))
        assert reader.display_name == "Existing" and not reader.active
        assert session.scalar(select(ReaderInvitation)).accepted_at is None
    assert state["calls"] == 0


@pytest.mark.anyio
async def test_operator_deletion_removes_used_invitation_data(database, invited_app):
    client, headers, state, _ = invited_app
    subject = uuid4()
    state["payload"] = google_user(subject)
    await client.post(
        "/api/invitations",
        headers=headers(),
        json={
            "email": EMAIL,
            "display_name": "Friend",
        },
    )
    assert (await client.get("/api/me", headers=headers(subject, EMAIL))).status_code == 200
    with Session(database) as session, session.begin():
        set_access(session, subject, active=False)
        delete_reader(session, subject)
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(ReaderInvitation)) == 0
    assert (await client.get("/api/me", headers=headers(subject, EMAIL))).status_code == 403
