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


def get_element_count_greater_than(config) -> Optional[int]:
    """Return the exclusive lower bound configured for element counts."""
    value = _filter_config(config).get("element_count_greater_than")
    if value in (None, ""):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(
            "monitor_filters.element_count_greater_than must be a non-negative integer"
        )
    return value


def extract_compound_formula(label: str) -> Optional[str]:
    """Return a validated formula from the start of a workflow label."""
    if not isinstance(label, str) or not label.strip():
        return None

    formula = re.split(r"[/_:]", label.strip(), maxsplit=1)[0].strip()
    symbols = _ELEMENT_PATTERN.findall(formula)
    if not symbols or any(symbol not in _ELEMENT_SYMBOLS for symbol in symbols):
        return None

    remainder = _ELEMENT_PATTERN.sub("", formula)
    if not _FORMULA_REMAINDER_PATTERN.fullmatch(remainder):
        return None

    return formula


def get_compound_elements(label: str) -> Optional[frozenset]:
    """Return distinct element symbols from the formula in a workflow label."""
    formula = extract_compound_formula(label)
    if formula is None:
        return None
    return frozenset(_ELEMENT_PATTERN.findall(formula))


def count_compound_elements(label: str) -> Optional[int]:
    """Count distinct elements in the formula at the start of a workflow label."""
    compound_elements = get_compound_elements(label)
    return len(compound_elements) if compound_elements is not None else None


def get_allowed_compounds(config) -> Optional[frozenset]:
    """Return exact compound formulas configured for inclusion."""
    raw_compounds = _filter_config(config).get("compounds")
    if raw_compounds in (None, "", []):
        return None
    if isinstance(raw_compounds, str):
        raw_compounds = [raw_compounds]
    if not isinstance(raw_compounds, Collection) or isinstance(
        raw_compounds, (bytes, Mapping)
    ):
        raise ValueError(
            "monitor_filters.compounds must contain formulas such as [BaMnO3, HgI2]"
        )

    normalized = set()
    for value in raw_compounds:
        if not isinstance(value, str):
            raise ValueError("compound filters must be chemical formula strings")
        value = value.strip()
        if extract_compound_formula(value) != value:
            raise ValueError(f"invalid compound formula {value!r}")
        normalized.add(value)
    return frozenset(normalized)


def get_element_filter(config) -> Tuple[Optional[frozenset], str]:
    """Return element symbols and their configured any/all matching mode."""
    options = _filter_config(config)
    match_mode = str(options.get("elements_match", "any")).strip().lower()
    if match_mode not in {"any", "all"}:
        raise ValueError("monitor_filters.elements_match must be 'any' or 'all'")

    raw_elements = options.get("elements")
    if raw_elements in (None, "", []):
        return None, match_mode
    if isinstance(raw_elements, str):
        raw_elements = [raw_elements]
    if not isinstance(raw_elements, Collection) or isinstance(
        raw_elements, (bytes, Mapping)
    ):
        raise ValueError(
            "monitor_filters.elements must contain symbols such as [Ba, Mn]"
        )

    normalized = set()
    for value in raw_elements:
        if not isinstance(value, str) or value.strip() not in _ELEMENT_SYMBOLS:
            raise ValueError(f"invalid chemical element symbol {value!r}")
        normalized.add(value.strip())
    return frozenset(normalized), match_mode


def matches_element_count(
    label: str,
    allowed_counts: Optional[Collection[int]] = None,
    greater_than: Optional[int] = None,
) -> bool:
    if allowed_counts is None and greater_than is None:
        return True
    count = count_compound_elements(label)
    if count is None:
        return False
    if allowed_counts is not None and count not in allowed_counts:
        return False
    return greater_than is None or count > greater_than


def matches_compound_filters(
    label: str,
    allowed_counts: Optional[Collection[int]] = None,
    greater_than: Optional[int] = None,
    allowed_compounds: Optional[Collection[str]] = None,
    selected_elements: Optional[Collection[str]] = None,
    elements_match: str = "any",
) -> bool:
    """Return whether a workflow label satisfies every enabled compound filter."""
    if not matches_element_count(label, allowed_counts, greater_than):
        return False

    if allowed_compounds is None and selected_elements is None:
        return True

    formula = extract_compound_formula(label)
    compound_elements = get_compound_elements(label)
    if formula is None or compound_elements is None:
        return False
    if allowed_compounds is not None and formula not in allowed_compounds:
        return False
    if selected_elements is None:
        return True
    if elements_match == "all":
        return set(selected_elements).issubset(compound_elements)
    return bool(set(selected_elements).intersection(compound_elements))


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
