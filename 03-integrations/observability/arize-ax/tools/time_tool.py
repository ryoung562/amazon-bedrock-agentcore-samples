"""Time tool for retrieving current time in different timezones."""

import logging
from datetime import datetime
from typing import Any

import pytz

logger = logging.getLogger(__name__)


def get_time(timezone: str) -> dict[str, Any]:
    """Get current time for a timezone.

    Args:
        timezone: The timezone name (e.g., 'America/New_York', 'Europe/London')

    Returns:
        Dictionary containing current time information
    """
    if not timezone or not isinstance(timezone, str):
        raise ValueError("Timezone must be a non-empty string")

    timezone_normalized = timezone.strip()
    if not timezone_normalized:
        raise ValueError("Timezone cannot be empty")

    logger.info("Getting time for timezone: %s", timezone_normalized)

    try:
        tz = pytz.timezone(timezone_normalized)
    except pytz.exceptions.UnknownTimeZoneError as e:
        raise ValueError(
            f"Unknown timezone: {timezone_normalized}. "
            "Use a valid timezone name like 'America/New_York' or 'Europe/London'"
        ) from e

    current_time = datetime.now(tz)

    return {
        "timezone": timezone_normalized,
        "time": current_time.strftime("%I:%M:%S %p"),
        "date": current_time.strftime("%Y-%m-%d"),
        "day_of_week": current_time.strftime("%A"),
        "iso_format": current_time.isoformat(),
    }
