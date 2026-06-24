"""Shared rate limiter instance (slowapi).

Defined separately to avoid circular import between main.py and routers.
main.py assigns it to app.state.limiter and registers the exception handler;
routers use @limiter.limit(...) decorator.
"""
from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address


limiter = Limiter(key_func=get_remote_address)
