"""
RouteCare AI - Authentication endpoints.

Thin HTTP layer over app.services.auth_service. See docs/05_API_Design.md
section 3 for the original endpoint shapes (extended here with
refresh_token support, which the original examples predate).
"""

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.core.rate_limiting import rate_limit_login, rate_limit_password_reset, rate_limit_register
from app.database.session import get_db
from app.models.user import User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LogoutRequest,
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    RegisterResponse,
    RequestPasswordResetRequest,
    RequestPasswordResetResponse,
    ResetPasswordRequest,
    TokenResponse,
    UserPublic,
)
from app.services import auth_service

router = APIRouter()


def _token_response(user: User, access_token: str, refresh_token: str) -> TokenResponse:
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserPublic.model_validate(user),
    )


@router.post(
    "/register",
    response_model=RegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit_register)],
)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> RegisterResponse:
    user = auth_service.register_clinic_and_admin(
        db,
        clinic_name=payload.clinic_name,
        first_name=payload.first_name,
        last_name=payload.last_name,
        email=payload.email,
        password=payload.password,
    )
    return RegisterResponse(message="Account created successfully.", user_id=user.id)


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(rate_limit_login)])
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    user, access_token, refresh_token = auth_service.authenticate_user(
        db, email=payload.email, password=payload.password, ip_address=request.client.host if request.client else None
    )
    return _token_response(user, access_token, refresh_token)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user, access_token, refresh_token = auth_service.refresh_access_token(db, raw_refresh_token=payload.refresh_token)
    return _token_response(user, access_token, refresh_token)


@router.post("/logout", response_model=MessageResponse)
def logout(payload: LogoutRequest, db: Session = Depends(get_db)) -> MessageResponse:
    auth_service.logout(db, raw_refresh_token=payload.refresh_token)
    return MessageResponse(message="Logged out successfully.")


@router.get("/me", response_model=UserPublic)
def me(current_user: User = Depends(get_current_user)) -> UserPublic:
    return UserPublic.model_validate(current_user)


@router.post("/change-password", response_model=MessageResponse)
def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageResponse:
    auth_service.change_password(
        db, user=current_user, current_password=payload.current_password, new_password=payload.new_password
    )
    return MessageResponse(message="Password changed successfully. Please log in again on other devices.")


@router.post(
    "/request-password-reset",
    response_model=RequestPasswordResetResponse,
    dependencies=[Depends(rate_limit_password_reset)],
)
def request_password_reset(
    payload: RequestPasswordResetRequest, db: Session = Depends(get_db)
) -> RequestPasswordResetResponse:
    raw_token = auth_service.request_password_reset(db, email=payload.email)
    response = RequestPasswordResetResponse(
        message="If an account with that email exists, a password reset link has been sent."
    )
    # Dev-only convenience: no email delivery service is integrated yet,
    # so expose the raw token outside production so the flow is testable.
    if settings.ENVIRONMENT != "production":
        response.reset_token = raw_token
    return response


@router.post("/reset-password", response_model=MessageResponse)
def reset_password(payload: ResetPasswordRequest, db: Session = Depends(get_db)) -> MessageResponse:
    auth_service.reset_password(db, raw_token=payload.token, new_password=payload.new_password)
    return MessageResponse(message="Password has been reset successfully.")
