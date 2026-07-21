#!/usr/bin/env python3

"""Unit tests for the shared boundary-narrowing helpers."""

import pytest

from compresso.libs import narrowing


@pytest.mark.unittest
class TestCoercingFamily:
    def test_coerce_int_accepts_numeric_scalars(self):
        # Regression origin: preloading enabled without a count compared int >= None
        assert narrowing.coerce_int(None) == 0
        assert narrowing.coerce_int("3") == 3
        assert narrowing.coerce_int(2.9) == 2
        assert narrowing.coerce_int("abc", 7) == 7
        assert narrowing.coerce_int(object(), 1) == 1

    def test_coerce_int_or_none_distinguishes_invalid_from_zero(self):
        assert narrowing.coerce_int_or_none("0") == 0
        assert narrowing.coerce_int_or_none("abc") is None
        assert narrowing.coerce_int_or_none(None) is None

    def test_coerce_float_accepts_numeric_strings(self):
        assert narrowing.coerce_float("1.5") == 1.5
        assert narrowing.coerce_float(None, 2.0) == 2.0
        assert narrowing.coerce_float_or_none("nope") is None


@pytest.mark.unittest
class TestStrictFamily:
    def test_strict_scalars_reject_other_types(self):
        assert narrowing.strict_str(1, "d") == "d"
        assert narrowing.strict_str_or_none(1) is None
        assert narrowing.strict_int("3", 9) == 9
        assert narrowing.strict_int_or_none(True) is None
        assert narrowing.strict_bool(1) is False
        assert narrowing.strict_float(3) == 3.0
        assert narrowing.strict_float_or_none("3") is None

    def test_bool_is_never_an_int(self):
        assert narrowing.strict_int(True, 5) == 5


@pytest.mark.unittest
class TestContainers:
    def test_string_keyed_dict_variants(self):
        assert narrowing.string_keyed_dict({"a": 1}) == {"a": 1}
        assert narrowing.string_keyed_dict({1: "a"}) == {}
        assert narrowing.string_keyed_dict_or_none({1: "a"}) is None
        assert narrowing.string_keyed_dicts([{"a": 1}, "x", {"b": 2}]) == [{"a": 1}, {"b": 2}]

    def test_mapping_dict_accepts_any_mapping(self):
        from collections import UserDict

        assert narrowing.mapping_dict(UserDict({"a": 1})) == {"a": 1}

    def test_int_list_modes(self):
        assert narrowing.int_list([1, "2", True]) == [1]
        assert narrowing.int_list([1, "2", True], coerce=True) == [1, 2, 1]

    def test_string_list_filters_and_defaults(self):
        assert narrowing.string_list(["a", 1, "b"]) == ["a", "b"]
        assert narrowing.string_list(None, ("x",)) == ["x"]
