"""Verify Supabase access tokens using public signing keys, never privileged API keys."""

from threading import Lock
from time import monotonic
from uuid import UUID

import jwt
from jwt import PyJWKClient, PyJWKClientConnectionError


class InvalidAccessToken(Exception):
    pass


class AuthenticationUnavailable(Exception):
    pass


class SupabaseVerifier:
    def __init__(self, supabase_url: str) -> None:
        self.issuer = f"{supabase_url}/auth/v1"
        self.keys = PyJWKClient(
            f"{self.issuer}/.well-known/jwks.json",
            cache_keys=False,
            lifespan=300,
            timeout=5,
            cooldown_duration=30,
        )
        self._lock = Lock()
        self._unavailable_until = 0.0

    def verify(self, token: str) -> UUID:
        return UUID(self.verify_claims(token)["sub"])

    def verify_claims(self, token: str) -> dict:
        try:
            if not token or len(token) > 16384 or len(token.partition(".")[0]) > 2048:
                raise InvalidAccessToken
            header = jwt.get_unverified_header(token)
            # Unverified header fields can select only from fixed algorithms and trusted keys.
            if (
                header.get("alg") not in ("ES256", "RS256")
                or not isinstance(header.get("kid"), str)
                or not 1 <= len(header["kid"]) <= 200
                or header.get("crit")
            ):
                raise InvalidAccessToken
            with self._lock:
                if monotonic() < self._unavailable_until:
                    raise AuthenticationUnavailable
                try:
                    key = self.keys.get_signing_key(header["kid"])
                except PyJWKClientConnectionError:
                    self._unavailable_until = monotonic() + 10
                    raise AuthenticationUnavailable from None
            if key.algorithm_name != header["alg"]:
                raise InvalidAccessToken
            claims = jwt.decode(
                token,
                key,
                algorithms=["ES256", "RS256"],
                issuer=self.issuer,
                audience="authenticated",
                options={
                    "require": ["iss", "aud", "sub", "exp", "iat", "role", "session_id"],
                    "strict_aud": True,
                },
            )
            if (
                claims["role"] != "authenticated"
                or claims.get("is_anonymous") is not False
                or type(claims["iat"]) is not int
                or type(claims["exp"]) is not int
                or claims["exp"] <= claims["iat"]
            ):
                raise InvalidAccessToken
            UUID(claims["session_id"])
            UUID(claims["sub"])
            return claims
        except (
            jwt.PyJWTError,
            ValueError,
            TypeError,
            AttributeError,
            RecursionError,
            OverflowError,
        ):
            # Never return token contents, issuer diagnostics, or network exception strings.
            raise InvalidAccessToken from None
