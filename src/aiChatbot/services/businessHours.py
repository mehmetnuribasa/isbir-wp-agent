"""
Business hours check service.
Determines if current time is outside configured business hours.
Adapted from İşbir-Whatsapp-Chatbot.
"""

import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)


def isOutsideBusinessHours(
    hoursStart: str = "08:00",
    hoursEnd: str = "18:00",
    timezone_name: str = "Europe/Istanbul",
    businessDays: str = "0,1,2,3,4",
) -> bool:
    """
    Check if the current time is outside business hours.
    
    Args:
        hoursStart: Business hours start time (HH:MM)
        hoursEnd: Business hours end time (HH:MM)
        timezone_name: Timezone name (e.g., Europe/Istanbul)
        businessDays: Comma-separated weekday numbers (0=Mon)
    
    Returns:
        True if outside business hours (bot should deliver OOH message)
    """
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo(timezone_name)
    except ImportError:
        from datetime import timezone
        tz = timezone.utc

    now = datetime.now(tz)

    # Parse business days (default Mon-Fri: 0-4)
    days: List[int] = [
        int(d.strip())
        for d in businessDays.split(",")
        if d.strip().isdigit()
    ]
    if now.weekday() not in days:
        return True  # Weekend or non-business day

    try:
        start = datetime.strptime(hoursStart, "%H:%M").time()
        end = datetime.strptime(hoursEnd, "%H:%M").time()
    except ValueError:
        return False  # Malformed config — don't block the bot

    return not (start <= now.time() <= end)


def getOutOfHoursMessage() -> str:
    """Get the standard out-of-hours message."""
    return (
        "Şu an mesai saatleri dışındayız.\n\n"
        "📅 Çalışma saatlerimiz: Hafta içi 08:00 - 18:00\n\n"
        "Acil teknik destek için:\n"
        "🛠️ +90 530 919 61 83 (WhatsApp - 7/24)\n\n"
        "Mesai saatlerimizde size daha ayrıntılı yardımcı olabiliriz. "
        "İyi günler! 👋"
    )
