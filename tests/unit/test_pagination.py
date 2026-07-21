#!/usr/bin/env python3

"""Tests for shared table and API pagination parsing."""

import pytest


@pytest.mark.unittest
def test_parse_page_params_coerces_wire_integers_without_coercing_booleans():
    from compresso.webserver.helpers.pagination import parse_page_params

    page = parse_page_params(
        {
            "start": "5",
            "length": "10",
            "search_value": "movie",
            "library_ids": [1, "2", True, 2.5],
        }
    )

    assert page.start == 5
    assert page.length == 10
    assert page.search_value == "movie"
    assert page.library_ids == (1, 2)
    assert page.draw is None


@pytest.mark.unittest
def test_parse_page_params_supports_datatables_nested_search_and_draw():
    from compresso.webserver.helpers.pagination import parse_page_params

    page = parse_page_params(
        {
            "draw": "3",
            "start": "0",
            "length": "25",
            "search": {"value": "needle"},
        },
        data_tables=True,
    )

    assert page.draw == 3
    assert page.search_value == "needle"


@pytest.mark.unittest
def test_parse_page_params_uses_safe_defaults_for_malformed_values():
    from compresso.webserver.helpers.pagination import parse_page_params

    page = parse_page_params({"start": True, "length": 2.5, "search_value": 4})

    assert page.start == 0
    assert page.length == 0
    assert page.search_value == ""
    assert page.library_ids == ()
