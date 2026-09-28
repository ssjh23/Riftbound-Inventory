import base64
import hashlib
from datetime import datetime, timedelta, timezone

import bcrypt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import TOKEN_EXPIRE_DAYS, jwt_secret
from .deps import get_db
from .models import User

_oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/token")

ALGORITHM = "HS256"


def _prehash(plain: str) -> bytes:
    """SHA-256 pre-hash so bcrypt always receives ≤44 bytes regardless of
    password length (bcrypt truncates at 72 bytes, which would make passwords
    that differ only beyond that point hash identically)."""
    return base64.b64encode(hashlib.sha256(plain.encode()).digest())


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(_prehash(plain), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(_prehash(plain), hashed.encode())


def create_access_token(user_id: int, username: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "username": username, "exp": expire},
        jwt_secret(),
        algorithm=ALGORITHM,
    )


def get_current_user(
    token: str = Depends(_oauth2),
    db: Session = Depends(get_db),
) -> User:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, jwt_secret(), algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise creds_exc
    user = db.get(User, user_id)
    if user is None:
        raise creds_exc
    return user
