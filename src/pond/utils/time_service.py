"""Time service for timezone-aware datetime handling using Pendulum."""

import os
from datetime import datetime

import httpx
import pendulum
from pendulum import DateTime


class TimeService:
    """Handles timezone detection and datetime formatting."""

    def __init__(self, timezone: str | None = None, geoip_url: str | None = None):
        """Initialize with optional timezone override.

        Args:
            timezone: Explicit timezone override
            geoip_url: URL for geoip service (None to disable geoip detection)
        """
        self.geoip_url = geoip_url
        self.timezone = timezone or self._detect_timezone()

    def _detect_timezone(self) -> str:
        """Detect timezone using cascade: env → geoip → system → UTC."""
        # Try environment variable first
        if tz := os.environ.get("POND_TIMEZONE"):
            try:
                pendulum.timezone(tz)  # Validate it
                return tz
            except Exception:  # noqa: S110
                pass

        # Try geoip detection if enabled
        if self.geoip_url and (tz := self._geoip_timezone()):
            return tz

        # Try system timezone
        try:
            return pendulum.local_timezone().name
        except Exception:  # noqa: S110
            pass

        # Default to UTC
        return "UTC"

    def now(self) -> DateTime:
        """Get current time in UTC."""
        return pendulum.now("UTC")

    def format_datetime(self, dt: datetime | DateTime, tz: str | None = None) -> str:
        """Format datetime for display in specified or default timezone."""
        # Ensure we have a Pendulum datetime
        if not isinstance(dt, DateTime):
            dt = pendulum.instance(dt)

        # Convert to target timezone
        timezone_str = tz or self.timezone
        dt_local = dt.in_timezone(timezone_str)

        # Format like "Monday, August 4, 2025, 12:42 p.m. PDT"
        formatted = dt_local.format("dddd, MMMM D, YYYY, h:mm A")

        # Get timezone abbreviation
        tz_abbr = dt_local.strftime("%Z")

        return f"{formatted} {tz_abbr}"

    def format_date(self, dt: datetime | DateTime) -> str:
        """Format date like 'Monday, August 4, 2025'."""
        if not isinstance(dt, DateTime):
            dt = pendulum.instance(dt)

        # Convert to target timezone
        dt_local = dt.in_timezone(self.timezone)
        return dt_local.format("dddd, MMMM D, YYYY")

    def format_time(self, dt: datetime | DateTime) -> str:
        """Format time like '7:03 a.m. PDT'."""
        if not isinstance(dt, DateTime):
            dt = pendulum.instance(dt)

        # Convert to target timezone
        dt_local = dt.in_timezone(self.timezone)

        # Format time
        time_str = dt_local.format("h:mm")
        period = dt_local.format("A").lower()

        # Get timezone abbreviation (PDT, PST, etc)
        # Pendulum doesn't have a direct method, so we use strftime
        tz_abbr = dt_local.strftime("%Z")

        return f"{time_str} {period[0]}.m. {tz_abbr}"

    def format_age(self, dt: datetime | DateTime) -> str:
        """Format as relative time with intuitive day references.

        Returns different formats based on when the event occurred:
        - Today: "N minutes/hours ago"
        - Yesterday: "yesterday, N hours ago"
        - This week (since Sunday): "Tuesday, N days ago"
        - Older: "N weeks/months/years ago"
        """
        if not isinstance(dt, DateTime):
            dt = pendulum.instance(dt)

        # Work in local timezone for calendar comparisons
        dt_local = dt.in_timezone(self.timezone)
        now_local = pendulum.now(self.timezone)

        # Future times
        if dt_local > now_local:
            return dt.diff_for_humans()

        # Calculate various differences
        diff = now_local.diff(dt_local)
        total_hours = diff.total_seconds() / 3600
        total_minutes = diff.total_seconds() / 60

        # Get calendar boundaries
        today_start = now_local.start_of('day')
        yesterday_start = today_start.subtract(days=1)
        this_week_start = now_local.start_of('week')  # Sunday at midnight

        # Today (since midnight)
        if dt_local >= today_start:
            if total_minutes < 1:
                return "just now"
            elif total_minutes < 60:
                minutes = int(total_minutes)
                return f"{minutes} minute{'s' if minutes != 1 else ''} ago"
            else:
                hours = int(total_hours)
                return f"{hours} hour{'s' if hours != 1 else ''} ago"

        # Yesterday (between last midnight and the midnight before)
        elif dt_local >= yesterday_start:
            hours = int(total_hours)
            return f"yesterday, {hours} hour{'s' if hours != 1 else ''} ago"

        # This week (since Sunday midnight)
        elif dt_local >= this_week_start:
            day_name = dt_local.format('dddd')
            # Calculate days more accurately - from start of that day to now
            days_since = (now_local.date() - dt_local.date()).days
            return f"{day_name}, {days_since} day{'s' if days_since != 1 else ''} ago"

        # Older than this week
        else:
            weeks = diff.days // 7
            months = diff.months
            years = diff.years

            if years > 0:
                return f"{years} year{'s' if years != 1 else ''} ago"
            elif months >= 2:  # Cutoff at 2 months (8 weeks)
                return f"{months} months ago"
            elif weeks > 0:
                return f"{weeks} week{'s' if weeks != 1 else ''} ago"
            else:
                # Shouldn't reach here, but fallback to days
                return f"{diff.days} days ago"

    def parse_interval(self, interval: str) -> pendulum.Duration:
        """Parse human-friendly intervals like '6 hours' or 'last week'.

        Uses pytimeparse to handle various formats:
        - "6 hours", "30 minutes", "1 day"
        - "1h30m", "2d", "1w"
        - "yesterday" (special case for 1 day)
        - "last week" (special case for 1 week)
        """
        import pytimeparse

        interval = interval.lower().strip()

        # Special cases that pytimeparse doesn't handle
        if interval == "yesterday":
            return pendulum.duration(days=1)
        elif interval == "last week":
            return pendulum.duration(weeks=1)

        # Remove "last" prefix if present (e.g., "last 6 hours" -> "6 hours")
        if interval.startswith("last "):
            interval = interval[5:]

        # Use pytimeparse to parse the interval
        seconds = pytimeparse.parse(interval)
        if seconds is None:
            raise ValueError(f"Invalid interval format: {interval}")

        return pendulum.duration(seconds=seconds)

    def get_day_label(self, dt: datetime | DateTime) -> str:
        """Get day label: 'Today', 'Yesterday', or day name (e.g., 'Tuesday')."""
        if not isinstance(dt, DateTime):
            dt = pendulum.instance(dt)

        # Convert to local timezone for comparison
        dt_local = dt.in_timezone(self.timezone)
        today = pendulum.now(self.timezone).date()
        dt_date = dt_local.date()

        if dt_date == today:
            return "Today"
        elif dt_date == today.subtract(days=1):
            return "Yesterday"
        else:
            # Return the day name (Monday, Tuesday, etc.)
            return dt_local.format("dddd")

    def get_date_key(self, dt: datetime | DateTime) -> str:
        """Get date key for grouping (YYYY-MM-DD format)."""
        if not isinstance(dt, DateTime):
            dt = pendulum.instance(dt)

        # Convert to local timezone for consistent grouping
        dt_local = dt.in_timezone(self.timezone)
        return dt_local.format("YYYY-MM-DD")

    def parse_datetime(self, dt_str: str) -> DateTime:
        """Parse various datetime formats.

        Accepts ISO-8601 formats and other common formats that Pendulum understands.
        Timezone-aware strings should use full timezone names (e.g., "America/New_York")
        or UTC offsets (e.g., "-07:00"), not abbreviations.
        """
        try:
            parsed = pendulum.parse(dt_str)
            # Ensure we return a DateTime, not Date or Time
            if isinstance(parsed, DateTime):
                return parsed
            else:
                # If it parsed to just a date, assume midnight UTC
                result = pendulum.parse(dt_str + " 00:00:00")
                assert isinstance(result, DateTime)  # Type narrowing
                return result
        except Exception as e:
            raise ValueError(f"Cannot parse datetime: {dt_str}") from e

    def _geoip_timezone(self) -> str | None:
        """Detect timezone from GeoIP."""
        if not self.geoip_url:
            return None

        try:
            response = httpx.get(self.geoip_url, timeout=5.0)
            response.raise_for_status()
            data = response.json()
            return data.get("timezone")
        except Exception:
            return None
