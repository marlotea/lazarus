"""Lazy access to the IBL ONE client.

Importing this module never connects or touches `~/.one`; `get_one()` does, on first call.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

from app.settings import get_settings

if TYPE_CHECKING:
    from one.api import OneAlyx

PUBLIC_PASSWORD = "international"  # public password of the openalyx server


@lru_cache
def get_one() -> OneAlyx:
    """Connect to the public IBL server (cached for the process)."""
    settings = get_settings()
    if settings.ibl_fake:
        raise RuntimeError("IBL_FAKE=1: refusing to connect to IBL. Use app.ibl.fake instead.")
    from one.api import ONE  # heavy import, deferred on purpose

    settings.one_cache_dir.mkdir(parents=True, exist_ok=True)
    return ONE(
        base_url=settings.one_base_url,
        password=PUBLIC_PASSWORD,
        silent=True,
        cache_dir=settings.one_cache_dir,
    )
