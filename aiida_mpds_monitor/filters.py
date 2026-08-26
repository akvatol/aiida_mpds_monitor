import math
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Collection, Mapping, Optional, Tuple

from aiida.common.constants import elements


_ELEMENT_PATTERN = re.compile(r"[A-Z][a-z]?")
_FORMULA_REMAINDER_PATTERN = re.compile(r"[\d\s().+\-\[\]·]*")
_ELEMENT_SYMBOLS = frozenset(
    element["symbol"] for atomic_number, element in elements.items() if atomic_number
)


def _filter_config(config) -> Mapping:
    value = config.get("monitor_filters", {}) or {}
    if not isinstance(value, Mapping):
        raise ValueError("monitor_filters must be a mapping")
    return value


def _parse_datetime(
    value, option_name: str, end_of_day: bool = False
) -> Optional[datetime]:
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if end_of_day else time.min)
    elif isinstance(value, str):
        try:
            text = value.strip()
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                parsed = datetime.combine(
                    date.fromisoformat(text), time.max if end_of_day else time.min
                )
            else:
                parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(
                f"monitor_filters.{option_name} must use YYYY-MM-DD or an ISO 8601 datetime"
            ) from exc
    else:
        raise ValueError(
            f"monitor_filters.{option_name} must use YYYY-MM-DD or an ISO 8601 datetime"
        )

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def get_time_bounds(
    config, now: Optional[datetime] = None
) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Return the inclusive parent creation-time bounds configured for monitoring."""
    options = _filter_config(config)
    created_after = _parse_datetime(options.get("created_after"), "created_after")
    created_before = _parse_datetime(
        options.get("created_before"), "created_before", end_of_day=True
    )

    max_age_hours = options.get("max_age_hours")
    if max_age_hours not in (None, ""):
        if isinstance(max_age_hours, bool):
            raise ValueError("monitor_filters.max_age_hours must be a positive number")
        try:
            max_age_hours = float(max_age_hours)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "monitor_filters.max_age_hours must be a positive number"
            ) from exc
        if not math.isfinite(max_age_hours) or max_age_hours <= 0:
            raise ValueError("monitor_filters.max_age_hours must be a positive number")

        current_time = now or datetime.now(timezone.utc)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=timezone.utc)
        rolling_after = current_time.astimezone(timezone.utc) - timedelta(
            hours=max_age_hours
        )
        if created_after is None or rolling_after > created_after:
            created_after = rolling_after

    if created_after and created_before and created_after > created_before:
        raise ValueError(
            "monitor_filters.created_after must not be later than created_before"
        )

    return created_after, created_before


def get_allowed_element_counts(config) -> Optional[frozenset]:
    """Return configured positive integer element counts."""
    raw_counts = _filter_config(config).get("element_counts")
    if raw_counts in (None, "", []):
        return None
    if isinstance(raw_counts, int) and not isinstance(raw_counts, bool):
        raw_counts = [raw_counts]
    if (
        not isinstance(raw_counts, Collection)
        or isinstance(raw_counts, (str, bytes, Mapping))
    ):
        raise ValueError(
            "monitor_filters.element_counts must contain positive integers such as [2, 3]"
        )

    normalized = set()
    for value in raw_counts:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("element counts must be positive integers")
        if value <= 0:
            raise ValueError("element counts must be positive integers")
        normalized.add(value)

    return frozenset(normalized)


def count_compound_elements(label: str) -> Optional[int]:
    """Count distinct elements in the formula at the start of a workflow label."""
    if not isinstance(label, str) or not label.strip():
        return None

    formula = re.split(r"[/_:]", label.strip(), maxsplit=1)[0].strip()
    symbols = _ELEMENT_PATTERN.findall(formula)
    if not symbols or any(symbol not in _ELEMENT_SYMBOLS for symbol in symbols):
        return None

    remainder = _ELEMENT_PATTERN.sub("", formula)
    if not _FORMULA_REMAINDER_PATTERN.fullmatch(remainder):
        return None

    return len(set(symbols))


def matches_element_count(label: str, allowed_counts: Optional[Collection[int]]) -> bool:
    if allowed_counts is None:
        return True
    count = count_compound_elements(label)
    return count is not None and count in allowed_counts


def build_parent_query_filters(config, workchain_types, now: Optional[datetime] = None):
    """Build AiiDA QueryBuilder filters for process type and parent creation time."""
    conditions = [
        {"attributes.process_label": {"in": list(workchain_types)}},
    ]
    created_after, created_before = get_time_bounds(config, now=now)
    if created_after:
        conditions.append({"ctime": {">=": created_after}})
    if created_before:
        conditions.append({"ctime": {"<=": created_before}})
    return conditions[0] if len(conditions) == 1 else {"and": conditions}
