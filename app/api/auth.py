from __future__ import annotations

from dataclasses import dataclass
from fastapi import Depends, Header, HTTPException, Request, status
import jwt

from app.config import Settings, get_settings


@dataclass(frozen=True)
class AuthContext:
    subject: str
    tenant_id: str


def _verify_oidc(token: str, settings: Settings) -> dict:
    if not settings.oidc_jwks_url or not settings.oidc_issuer:
        raise HTTPException(status_code=500, detail='OIDC settings are incomplete')
    try:
        jwks_client = jwt.PyJWKClient(settings.oidc_jwks_url)
        signing_key = jwks_client.get_signing_key_from_jwt(token).key
        options = {'verify_aud': bool(settings.oidc_audience)}
        return jwt.decode(
            token,
            signing_key,
            algorithms=['RS256', 'ES256'],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer,
            options=options,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Invalid access token') from exc


def get_auth_context(
    request: Request,
    settings: Settings = Depends(get_settings),
    x_dev_user: str | None = Header(default=None, alias='X-Dev-User'),
    x_dev_tenant: str | None = Header(default=None, alias='X-Dev-Tenant'),
) -> AuthContext:
    if settings.auth_mode == 'dev':
        return AuthContext(
            subject=x_dev_user or settings.default_subject,
            tenant_id=x_dev_tenant or settings.default_tenant_id,
        )

    authorization = request.headers.get('authorization', '')
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Bearer token required')
    claims = _verify_oidc(authorization.split(' ', 1)[1], settings)
    subject = claims.get('sub')
    tenant_id = claims.get('tenant_id') or claims.get('org_id')
    if not subject or not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Token lacks subject/tenant scope')
    return AuthContext(subject=subject, tenant_id=str(tenant_id))
