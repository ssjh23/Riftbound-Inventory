from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth import create_access_token, hash_password, verify_password
from ..deps import get_db
from ..models import User
from ..schemas import RegisterRequest, TokenOut, TokenRequest, UserOut

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == body.username).first():
        raise HTTPException(status.HTTP_409_CONFLICT, "Username already taken")
    user = User(username=body.username, hashed_password=hash_password(body.password))
    db.add(user)
    db.commit()
    db.refresh(user)

    # First ever user — adopt any inventory rows left without an owner.
    if db.query(User).count() == 1:
        db.execute(
            text("UPDATE inventory SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": user.id},
        )
        db.commit()

    return UserOut(id=user.id, username=user.username)


@router.post("/token", response_model=TokenOut)
def login(body: TokenRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenOut(
        access_token=create_access_token(user.id, user.username),
        username=user.username,
    )
