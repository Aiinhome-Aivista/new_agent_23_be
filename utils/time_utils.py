from datetime import datetime, timezone, timedelta

# Indian Standard Time (IST) offset: UTC + 5 hours 30 minutes
IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    """Returns the current timezone-aware datetime in Indian Standard Time (IST)."""
    return datetime.now(IST_OFFSET)

def get_ist_string(fmt: str = "%Y-%m-%d %I:%M:%S %p IST") -> str:
    """Returns the current formatted Indian Standard Time string."""
    return get_ist_now().strftime(fmt)
