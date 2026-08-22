"""
RouteCare AI - Rate limiting extension points.

No rate-limiting backend is wired up yet (no Redis-backed limiter, no
slowapi). These dependencies are intentional no-ops so the auth routes
already declare *where* limits belong; wire a real implementation into
the function bodies below without touching any router.

Suggested production behavior once a backend is chosen:
- rate_limit_login: ~5 attempts / 15 min per (ip, email) pair
- rate_limit_password_reset: ~3 requests / hour per (ip, email) pair
- rate_limit_register: ~5 requests / hour per ip
"""

from fastapi import Request


async def rate_limit_login(request: Request) -> None:
    # TODO(rate-limiting): enforce attempt limits per IP + email.
    return None


async def rate_limit_password_reset(request: Request) -> None:
    # TODO(rate-limiting): enforce request limits per IP + email.
    return None


async def rate_limit_register(request: Request) -> None:
    # TODO(rate-limiting): enforce request limits per IP.
    return None
