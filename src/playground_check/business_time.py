"""Business dates use Winterthur local time, independently of the server clock."""
from datetime import datetime
from zoneinfo import ZoneInfo

BUSINESS_ZONE = ZoneInfo("Europe/Zurich")


def local_now():
    # Existing transfer columns are local timestamps without time zone.
    return datetime.now(BUSINESS_ZONE).replace(tzinfo=None)


def local_today():
    return local_now().date()
