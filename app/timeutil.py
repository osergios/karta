from datetime import datetime

from . import config


def now_local() -> datetime:
    """Current Europe/Athens wall time, naive, second precision (what Ergani expects)."""
    return datetime.now(config.TZ).replace(tzinfo=None, microsecond=0)
