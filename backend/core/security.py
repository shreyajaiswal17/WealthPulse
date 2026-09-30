import httpx
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from functools import lru_cache
from core.config import settings
import json

ALGORITHMS = ["RS256"]

bearer_scheme = HTTPBearer()


@lru_cache(maxsize=1)
def _fetch_jwks() -> dict:
    """Fetch Auth0 JWKS synchronously (cached for the process lifetime).

    python-jose requires a dict of the JWKS. The lru_cache means we only
    hit the network once per worker process. If Auth0 ever rotates keys,
    restart the server (or bump maxsize / add a TTL wrapper).
    """
    url = f"https://{settings.AUTH0_DOMAIN}/.well-known/jwks.json"
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json()


def _get_signing_key(token: str, jwks: dict):
    """Extract the signing key from JWKS based on token's kid (key ID)."""
    try:
        # Decode header without verification to get kid
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        if not kid:
            raise JWTError("Token header missing 'kid' field")

        # Find the key with matching kid in JWKS
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                return key

        raise JWTError(f"Unable to find key with kid: {kid}")
    except Exception as e:
        raise JWTError(f"Failed to get signing key: {str(e)}")


async def get_current_user(request: Request):
    """Validate JWT token from Auth0 with signature, audience, and issuer verification."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        print("[JWT] No Bearer token found in Authorization header")
        raise HTTPException(status_code=401, detail="Not authenticated")

    token = auth[7:]
    try:
        print(f"[JWT] Validating token (first 50 chars): {token[:50]}...")

        # Fetch JWKS from Auth0
        jwks = _fetch_jwks()
        print(f"[JWT] JWKS fetched, contains {len(jwks.get('keys', []))} keys")

        # Get the signing key for this token
        signing_key = _get_signing_key(token, jwks)
        print(f"[JWT] Found signing key with kid")

        # Decode and validate JWT using the signing key
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=ALGORITHMS,
            audience=settings.AUTH0_AUDIENCE,
            issuer=f"https://{settings.AUTH0_DOMAIN}/",
        )
        print(f"[JWT] Token validated successfully, subject: {payload.get('sub')}")
        return payload
    except JWTError as e:
        error_msg = f"JWT validation failed: {str(e)}"
        print(f"[JWT ERROR] {error_msg}")
        raise HTTPException(status_code=401, detail=error_msg)
    except Exception as e:
        error_msg = f"Token validation error: {str(e)}"
        print(f"[JWT ERROR] {error_msg}")
        raise HTTPException(status_code=401, detail=error_msg)
