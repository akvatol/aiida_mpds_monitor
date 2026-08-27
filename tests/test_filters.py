from datetime import date, datetime, timezone

import pytest

from aiida_mpds_monitor.filters import (
    build_parent_query_filters,
    count_compound_elements,
    extract_compound_formula,
    get_allowed_compounds,
    get_allowed_element_counts,
    get_compound_elements,
    get_element_count_greater_than,
    get_element_filter,
    get_time_bounds,
    matches_compound_filters,
)


@pytest.mark.parametrize(
    "label, formula, count",
    [
        ("BaMnO3/185: Geometry optimization", "BaMnO3", 3),
        ("Fe2(SO4)3/1: Relax", "Fe2(SO4)3", 3),
        ("NaCl_225_cF8", "NaCl", 2),
        ("La0.5Sr0.5MnO3: Relax", "La0.5Sr0.5MnO3", 4),
        ("Geometry optimization", None, None),
        ("", None, None),
    ],
)
def test_formula_extraction_and_element_count(label, formula, count):
    assert extract_compound_formula(label) == formula
    assert count_compound_elements(label) == count


def test_exact_compound_filter_uses_leading_label_formula():
    compounds = {"BaMnO3", "HgI2"}

    assert matches_compound_filters(
        "BaMnO3/185: Geometry optimization", allowed_compounds=compounds
    )
    assert not matches_compound_filters(
        "Ba2MnO4/1: Geometry optimization", allowed_compounds=compounds
    )


def test_element_filter_any_mode():
    assert matches_compound_filters(
        "BaTiO3/1: Relax", selected_elements={"Mn", "Ba"}, elements_match="any"
    )
    assert not matches_compound_filters(
        "CaTiO3/1: Relax", selected_elements={"Mn", "Ba"}, elements_match="any"
    )


def test_element_filter_all_mode():
    assert matches_compound_filters(
        "BaMnO3/1: Relax", selected_elements={"Ba", "Mn"}, elements_match="all"
    )
    assert not matches_compound_filters(
        "BaTiO3/1: Relax", selected_elements={"Ba", "Mn"}, elements_match="all"
    )


def test_compound_filters_are_combined_with_count_threshold():
    assert matches_compound_filters(
        "BaMnO3/1: Relax",
        greater_than=2,
        allowed_compounds={"BaMnO3"},
        selected_elements={"Mn"},
    )
    assert not matches_compound_filters(
        "HgI2/1: Relax",
        greater_than=2,
        allowed_compounds={"HgI2"},
        selected_elements={"Hg"},
    )


def test_compound_and_element_config_normalization():
    config = {
        "monitor_filters": {
            "compounds": ["BaMnO3", "HgI2"],
            "elements": ["Ba", "Mn"],
            "elements_match": "ALL",
        }
    }

    assert get_allowed_compounds(config) == frozenset({"BaMnO3", "HgI2"})
    assert get_element_filter(config) == (frozenset({"Ba", "Mn"}), "all")
    assert get_compound_elements("BaMnO3/185: Relax") == frozenset(
        {"Ba", "Mn", "O"}
    )


def test_empty_compound_and_element_filters_are_disabled():
    assert get_allowed_compounds({}) is None
    assert get_element_filter({}) == (None, "any")
    assert matches_compound_filters("label without formula")


def test_element_count_configuration_and_strict_threshold():
    config = {
        "monitor_filters": {
            "element_counts": [2, 3],
            "element_count_greater_than": 2,
        }
    }

    assert get_allowed_element_counts(config) == frozenset({2, 3})
    assert get_element_count_greater_than(config) == 2
    assert matches_compound_filters(
        "BaMnO3/1: Relax", allowed_counts={2, 3}, greater_than=2
    )
    assert not matches_compound_filters(
        "HgI2/1: Relax", allowed_counts={2, 3}, greater_than=2
    )


@pytest.mark.parametrize(
    "value",
    [["2"], [0], [-1], [True], {"count": 2}],
)
def test_invalid_exact_element_counts_are_rejected(value):
    with pytest.raises(ValueError, match="positive integers"):
        get_allowed_element_counts({"monitor_filters": {"element_counts": value}})


@pytest.mark.parametrize("value", ["2", 2.0, -1, True, [2]])
def test_invalid_element_count_threshold_is_rejected(value):
    with pytest.raises(ValueError, match="non-negative integer"):
        get_element_count_greater_than(
            {"monitor_filters": {"element_count_greater_than": value}}
        )


@pytest.mark.parametrize("formula", ["not-a-formula", "BaMnO3/185", 123])
def test_invalid_compound_filter_is_rejected(formula):
    with pytest.raises(ValueError):
        get_allowed_compounds({"monitor_filters": {"compounds": [formula]}})


@pytest.mark.parametrize("symbol", ["ba", "Xx", 56])
def test_invalid_element_symbol_is_rejected(symbol):
    with pytest.raises(ValueError, match="invalid chemical element"):
        get_element_filter({"monitor_filters": {"elements": [symbol]}})


def test_invalid_element_match_mode_is_rejected():
    with pytest.raises(ValueError, match="any.*all"):
        get_element_filter({"monitor_filters": {"elements_match": "none"}})


def test_date_only_time_window_includes_both_complete_days():
    config = {
        "monitor_filters": {
            "created_after": date(2026, 8, 1),
            "created_before": "2026-08-31",
        }
    }

    created_after, created_before = get_time_bounds(config)

    assert created_after == datetime(2026, 8, 1, tzinfo=timezone.utc)
    assert created_before == datetime(
        2026, 8, 31, 23, 59, 59, 999999, tzinfo=timezone.utc
    )


def test_rolling_window_uses_more_restrictive_created_after():
    now = datetime(2026, 8, 27, 12, tzinfo=timezone.utc)
    config = {
        "monitor_filters": {
            "created_after": "2026-08-01",
            "max_age_hours": 24,
        }
    }

    created_after, created_before = get_time_bounds(config, now=now)

    assert created_after == datetime(2026, 8, 26, 12, tzinfo=timezone.utc)
    assert created_before is None


@pytest.mark.parametrize(
    "options",
    [
        {"created_after": "not-a-date"},
        {"max_age_hours": 0},
        {"max_age_hours": float("inf")},
        {
            "created_after": "2026-08-02",
            "created_before": "2026-08-01",
        },
    ],
)
def test_invalid_time_filters_are_rejected(options):
    with pytest.raises(ValueError):
        get_time_bounds({"monitor_filters": options})


def test_parent_query_combines_process_and_time_filters():
    config = {
        "monitor_filters": {
            "created_after": "2026-08-01",
            "created_before": "2026-08-31",
        }
    }

    result = build_parent_query_filters(config, ["MPDSStructureWorkChain"])

    assert result == {
        "and": [
            {
                "attributes.process_label": {
                    "in": ["MPDSStructureWorkChain"]
                }
            },
            {"ctime": {">=": datetime(2026, 8, 1, tzinfo=timezone.utc)}},
            {
                "ctime": {
                    "<=": datetime(
                        2026, 8, 31, 23, 59, 59, 999999, tzinfo=timezone.utc
                    )
                }
            },
        ]
    }
