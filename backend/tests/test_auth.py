import json
from base64 import urlsafe_b64encode
from io import BytesIO
from time import time
from urllib.error import URLError
from uuid import uuid4

import jwt
import pytest
from alembic import command
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import func, insert, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.access import invite_reader, link_owner, main, set_access
from app.auth import InvalidAccessToken, SupabaseVerifier
from app.config import Settings
from app.db import create_database_engine
from app.main import create_app
from app.models import LOCAL_OWNER_ID, AppUser, Article, ArticleReadState, Source, Subscription

ORIGIN = "https://project-example.supabase.co"


@pytest.fixture
def signing(monkeypatch):
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    public.update(kid="key-one", alg="ES256", use="sig")
    state = {"keys": [public], "calls": 0, "error": False}

    def fetch(_opener, request, **kwargs):
        assert request.full_url == f"{ORIGIN}/auth/v1/.well-known/jwks.json"
        assert kwargs["timeout"] == 5
        state["calls"] += 1
        if state["error"]:
            raise URLError("private diagnostic must not escape")
        return BytesIO(json.dumps({"keys": state["keys"]}).encode())

    monkeypatch.setattr("urllib.request.OpenerDirector.open", fetch)

    def token(subject=None, *, changes=None, headers=None, key=None, algorithm="ES256", omit=()):
        now = int(time())
        claims = {
            "iss": f"{ORIGIN}/auth/v1",
            "aud": "authenticated",
            "sub": str(subject or uuid4()),
            "iat": now - 1,
            "exp": now + 300,
            "role": "authenticated",
            "session_id": str(uuid4()),
            "is_anonymous": False,
        }
        claims.update(changes or {})
        for field in omit:
            claims.pop(field, None)
        return jwt.encode(
            claims,
            key or private,
            algorithm=algorithm,
            headers={"kid": "key-one"} | (headers or {}),
        )

    return token, state


@pytest.fixture
async def authenticated(database, signing):
    app = create_app(
        Settings(
            _env_file=None,
            database_url=database.url.render_as_string(hide_password=False),
            supabase_url=ORIGIN,
            scheduler_enabled=False,
        )
    )
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app, client=("198.51.100.1", 123)), base_url="http://test"
        ) as client:
            yield client, app


@pytest.mark.anyio
async def test_real_tokens_require_explicit_access_and_preserve_owner(
    database, signing, authenticated
):
    token, state = signing
    client, app = authenticated
    owner, reader, stranger = uuid4(), uuid4(), uuid4()
    # Even a valid token whose subject equals the reserved local ID cannot claim ownership.
    for subject in (owner, reader, stranger, LOCAL_OWNER_ID):
        result = await client.get("/api/me", headers={"Authorization": f"Bearer {token(subject)}"})
        assert result.status_code == 403
    with Session(database) as session, session.begin():
        source = Source(name="Shared", feed_url="https://example.org/rss")
        session.add(source)
        session.flush()
        article = Article(source_id=source.id, title="Shared", url="https://example.org/a")
        session.add(article)
        session.flush()
        source_id, article_id = source.id, article.id
        session.add_all(
            [
                Subscription(user_id=LOCAL_OWNER_ID, source_id=source_id),
                ArticleReadState(user_id=LOCAL_OWNER_ID, article_id=article_id),
            ]
        )
        assert link_owner(session, owner) == LOCAL_OWNER_ID
        reader_id = invite_reader(session, reader, "Friend")
    owner_headers = {"Authorization": f"Bearer {token(owner)}"}
    elevated_metadata = {
        "user_metadata": {"role": "admin", "user_id": str(LOCAL_OWNER_ID)},
        "app_metadata": {"role": "admin"},
    }
    reader_headers = {"Authorization": f"Bearer {token(reader, changes=elevated_metadata)}"}
    assert (await client.get("/api/me", headers=owner_headers)).json()["id"] == str(LOCAL_OWNER_ID)
    assert (await client.get("/api/articles", headers=owner_headers)).json()["items"][0]["is_read"]
    assert (await client.get("/api/me", headers=reader_headers)).json()["role"] == "reader"
    assert (
        await client.post(
            "/api/categories", headers=reader_headers, json={"name": "No", "slug": "no"}
        )
    ).status_code == 403
    assert (
        await client.put(f"/api/subscriptions/{source_id}", headers=reader_headers)
    ).status_code == 204
    assert not (await client.get("/api/articles", headers=reader_headers)).json()["items"][0][
        "is_read"
    ]
    with Session(database) as session, session.begin():
        set_access(session, reader, active=False)
    assert (await client.get("/api/me", headers=reader_headers)).status_code == 403
    with Session(database) as session, session.begin():
        assert invite_reader(session, reader, "Renamed") == reader_id
        assert not session.get(AppUser, reader_id).active
        set_access(session, reader, active=True)
    assert (await client.get("/api/subscriptions", headers=reader_headers)).json()["total"] == 1
    assert state["calls"] == 1
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(AppUser)) == 2


@pytest.mark.anyio
@pytest.mark.parametrize(
    "changes",
    [
        {"iss": "https://other.supabase.co/auth/v1"},
        {"aud": "other"},
        {"aud": ["authenticated", "other"]},
        {"role": "service_role"},
        {"role": "anon"},
        {"role": "admin"},
        {"is_anonymous": True},
        {"is_anonymous": "false"},
        {"sub": "not-a-uuid"},
        {"session_id": "not-a-uuid"},
        {"session_id": None},
        {"exp": 1},
        {"iat": 4102444800},
        {"nbf": 4102444800},
        {"exp": "4102444800"},
    ],
)
async def test_bad_claims_fail_closed(authenticated, signing, changes):
    token, _ = signing
    client, _ = authenticated
    response = await client.get(
        "/api/me", headers={"Authorization": f"Bearer {token(changes=changes)}"}
    )
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"detail": "Invalid access token"}


@pytest.mark.parametrize(
    "claim", ["iss", "aud", "sub", "exp", "iat", "role", "session_id", "is_anonymous"]
)
def test_required_claims(signing, claim):
    token, _ = signing
    with pytest.raises(InvalidAccessToken):
        SupabaseVerifier(ORIGIN).verify(token(omit=[claim]))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "authorization", [None, "", "Basic abc", "Bearer", "Bearer a b", "Bearer malformed"]
)
async def test_missing_or_malformed_authorization(authenticated, authorization):
    client, _ = authenticated
    headers = {"Authorization": authorization} if authorization is not None else {}
    # Neither cookies nor URL/header identity selectors are authentication.
    headers.update({"Cookie": "access_token=forged", "x-user-id": str(LOCAL_OWNER_ID)})
    assert (
        await client.get(f"/api/me?access_token=forged&user_id={LOCAL_OWNER_ID}", headers=headers)
    ).status_code == 401
    assert (await client.get("/api/health", headers=headers)).status_code == 200


def test_bad_signatures_algorithms_and_untrusted_key_urls(signing):
    token, state = signing
    verifier = SupabaseVerifier(ORIGIN)
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token(key=ec.generate_private_key(ec.SECP256R1())))
    for algorithm in ("HS256", "HS384"):
        with pytest.raises(InvalidAccessToken):
            verifier.verify(token(key="x" * 64, algorithm=algorithm))
    with pytest.raises(InvalidAccessToken):
        verifier.verify(
            jwt.encode({"sub": str(uuid4())}, "", algorithm="none", headers={"kid": "key-one"})
        )
    with pytest.raises(InvalidAccessToken):
        verifier.verify("a" * 16385)
    subject = uuid4()
    assert verifier.verify(token(subject, headers={"jku": "http://127.0.0.1/private"})) == subject
    assert state["calls"] == 1


def test_oversized_nested_header_is_rejected_without_network(signing):
    _, state = signing
    header = '{"alg":"ES256","kid":"key-one","extra":' + "[" * 1200 + "0" + "]" * 1200 + "}"
    encoded = urlsafe_b64encode(header.encode()).decode().rstrip("=")
    with pytest.raises(InvalidAccessToken):
        SupabaseVerifier(ORIGIN).verify(f"{encoded}.e30.YQ")
    assert state["calls"] == 0


def test_rsa_signatures(signing):
    token, state = signing
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    public.update(kid="key-one", alg="RS256", use="sig")
    state["keys"] = [public]
    subject = uuid4()
    assert (
        SupabaseVerifier(ORIGIN).verify(token(subject, key=private, algorithm="RS256")) == subject
    )


def test_key_cache_rotation_and_unknown_key_cooldown(signing, monkeypatch):
    token, state = signing
    verifier = SupabaseVerifier(ORIGIN)
    subject = uuid4()
    assert verifier.verify(token(subject)) == subject
    for index in range(10):
        with pytest.raises(InvalidAccessToken):
            verifier.verify(token(headers={"kid": f"unknown-{index}"}))
    assert state["calls"] == 1
    # Simulate expiry through the documented JWK-set cache, not per-key permanent caching.
    private = ec.generate_private_key(ec.SECP256R1())
    public = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    public.update(kid="key-two", alg="ES256", use="sig")
    state["keys"] = [public]
    verifier.keys.jwk_set_cache.put(None)
    assert verifier.verify(token(subject, key=private, headers={"kid": "key-two"})) == subject
    with pytest.raises(InvalidAccessToken):
        verifier.verify(token(subject))
    assert state["calls"] == 2


@pytest.mark.anyio
async def test_jwks_outage_is_bounded_and_does_not_disclose_diagnostics(authenticated, signing):
    token, state = signing
    state["error"] = True
    client, _ = authenticated
    for _ in range(3):
        response = await client.get("/api/me", headers={"Authorization": f"Bearer {token()}"})
        assert response.status_code == 503
        assert response.headers["retry-after"] == "10"
        assert "private" not in response.text
    assert state["calls"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://example.org",
        "https://user:secret@example.org",
        "https://example.org/auth/v1",
        "https://example.org?x=1",
        "https://example.org#fragment",
        "https://example.org:5432",
        "https://",
        "https://example.org/ other",
    ],
)
def test_bad_auth_configuration(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, supabase_url=url)


def test_no_local_fallback_with_supabase():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, supabase_url=ORIGIN, local_user_id=LOCAL_OWNER_ID)
    assert Settings(_env_file=None, supabase_url=ORIGIN + "/").supabase_url == ORIGIN


def test_explicit_link_is_unique_immutable_and_never_changes_roles(database):
    owner, other = uuid4(), uuid4()
    with Session(database) as session, session.begin():
        link_owner(session, owner)
        assert link_owner(session, owner) == LOCAL_OWNER_ID
        with pytest.raises(ValueError):
            link_owner(session, other)
        with pytest.raises(ValueError):
            invite_reader(session, owner, "Not a reader")
        with pytest.raises(ValueError):
            set_access(session, other, active=True)
        with pytest.raises(ValueError):
            invite_reader(session, other, " ")
    with Session(database) as session:
        session.add(AppUser(display_name="Duplicate", supabase_subject=owner))
        with pytest.raises(IntegrityError):
            session.commit()


def test_operator_commands_use_configured_database_without_cloud_calls(
    database, monkeypatch, capsys
):
    import app.access as access

    settings = Settings(
        _env_file=None,
        supabase_url=ORIGIN,
        database_url=database.url.render_as_string(hide_password=False),
    )
    monkeypatch.setattr(access, "Settings", lambda: settings)
    owner, reader = str(uuid4()), str(uuid4())
    assert main(["link-owner", "--subject", owner]) == 0
    assert main(["invite", "--subject", reader, "--name", "Friend"]) == 0
    assert main(["revoke", "--subject", reader]) == 0
    assert main(["activate", "--subject", reader]) == 0
    assert main(["link-owner", "--subject", reader]) == 1
    assert "Traceback" not in capsys.readouterr().out


def test_0004_preserves_profiles_and_personal_data(migration_config):
    command.upgrade(migration_config, "0003")
    engine = create_database_engine(migration_config.get_main_option("sqlalchemy.url"))
    try:
        # Old schema has no supabase_subject column, so use SQL instead of new model queries.
        with engine.begin() as connection:
            connection.exec_driver_sql("UPDATE app_users SET display_name = 'Existing owner'")
        with Session(engine) as session, session.begin():
            source_id = session.scalar(
                insert(Source)
                .values(name="Existing", feed_url="https://example.org/rss")
                .returning(Source.id)
            )
            article_id = session.scalar(
                insert(Article)
                .values(source_id=source_id, title="Existing", url="https://example.org/a")
                .returning(Article.id)
            )
            session.add_all(
                [
                    Subscription(user_id=LOCAL_OWNER_ID, source_id=source_id),
                    ArticleReadState(user_id=LOCAL_OWNER_ID, article_id=article_id),
                ]
            )
        command.upgrade(migration_config, "head")
        with Session(engine) as session:
            user = session.get(AppUser, LOCAL_OWNER_ID)
            assert user.display_name == "Existing owner"
            assert user.role == "admin" and user.active and user.supabase_subject is None
            assert session.get(Subscription, (LOCAL_OWNER_ID, source_id)) is not None
            assert session.get(ArticleReadState, (LOCAL_OWNER_ID, article_id)) is not None
        command.check(migration_config)
        command.downgrade(migration_config, "0003")
        assert "supabase_subject" not in {
            col["name"] for col in inspect(engine).get_columns("app_users")
        }
        command.upgrade(migration_config, "head")
        command.check(migration_config)
        with Session(engine) as session:
            assert session.get(Subscription, (LOCAL_OWNER_ID, source_id)) is not None
            assert session.get(ArticleReadState, (LOCAL_OWNER_ID, article_id)) is not None
    finally:
        engine.dispose()
