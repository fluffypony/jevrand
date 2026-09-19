from decimal import Decimal, localcontext

import pytest

from jevrand.errors import ValidationError
from jevrand.numbers import (
    MAX_DECIMALS,
    MAX_SAFE_INTEGER,
    NumberRange,
    native_number,
    parse_number,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (0, Decimal("0")),
        (-23, Decimal("-23")),
        (1.25, Decimal("1.25")),
        (" -1.250 ", Decimal("-1.250")),
        ("2.5e2", Decimal("250")),
        (Decimal("0.000000001"), Decimal("0.000000001")),
        (MAX_SAFE_INTEGER, Decimal(MAX_SAFE_INTEGER)),
        (-MAX_SAFE_INTEGER, Decimal(-MAX_SAFE_INTEGER)),
    ],
)
def test_parse_number_preserves_finite_values(value, expected):
    assert parse_number(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        True,
        False,
        None,
        [],
        1 + 2j,
        object(),
        "",
        "   ",
        "twelve",
        "1.2.3",
        "NaN",
        "sNaN",
        "Infinity",
        "-Infinity",
        float("nan"),
        float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        MAX_SAFE_INTEGER + 1,
        -MAX_SAFE_INTEGER - 1,
        "1" * 101,
        "1e1000000",
        "-1e1000000",
        "9007199254740991.0000000000001",
        "-9007199254740991.0000000000001",
    ],
)
def test_parse_number_rejects_invalid_or_unsafe_values(value):
    with pytest.raises(ValidationError):
        parse_number(value)


def test_parse_number_rejects_enormous_integer_without_leaking_conversion_error():
    with pytest.raises(ValidationError):
        parse_number(10**5000)


@pytest.mark.parametrize("decimals", [-1, MAX_DECIMALS + 1, 1.0, True, False, "2", None])
def test_decimal_places_require_a_supported_integer(decimals):
    with pytest.raises(ValidationError):
        NumberRange.create(0, 10, decimals)


@pytest.mark.parametrize("bottom, top", [(2, 1), (-1, -2), ("0.02", "0.01")])
def test_reversed_range_is_invalid(bottom, top):
    with pytest.raises(ValidationError):
        NumberRange.create(bottom, top, 2)


@pytest.mark.parametrize(
    ("bottom", "top", "decimals", "first", "last", "expected"),
    [
        (0, 10000, 0, 0, 10000, (0, 10000)),
        (-20, -10, 0, -20, -10, (-20, -10)),
        (-2, 3, 0, -2, 3, (-2, 3)),
        ("0.1", "2.9", 0, 1, 2, (1, 2)),
        ("-2.9", "-0.1", 0, -2, -1, (-2, -1)),
        ("1.001", "1.029", 2, 101, 102, (1.01, 1.02)),
        ("-1.029", "-1.001", 2, -102, -101, (-1.02, -1.01)),
        ("-0.019", "0.019", 2, -1, 1, (-0.01, 0.01)),
        ("0.000000001", "0.000000003", 9, 1, 3, (0.000000001, 0.000000003)),
    ],
)
def test_draw_includes_both_grid_boundaries(
    monkeypatch, bottom, top, decimals, first, last, expected
):
    number_range = NumberRange.create(bottom, top, decimals)
    width = last - first + 1
    calls = []
    offsets = iter((0, width - 1))

    def draw_offset(stop):
        calls.append(stop)
        return next(offsets)

    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", draw_offset)

    assert (number_range.first, number_range.last) == (first, last)
    assert (number_range.draw(), number_range.draw()) == expected
    assert calls == [width, width]


@pytest.mark.parametrize("value, decimals", [(7, 0), (-7, 0), (0, 9), ("1.23", 2)])
def test_equal_grid_boundaries_draw_the_only_value(monkeypatch, value, decimals):
    calls = []

    def only_offset(stop):
        calls.append(stop)
        return 0

    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", only_offset)
    number_range = NumberRange.create(value, value, decimals)

    assert Decimal(str(number_range.draw())) == Decimal(str(value))
    assert calls == [1]


@pytest.mark.parametrize(
    ("bottom", "top", "decimals"),
    [
        ("0.1", "0.9", 0),
        ("-0.9", "-0.1", 0),
        ("1.231", "1.239", 2),
        ("1.234", "1.234", 2),
        ("1e-2000000", "1e-2000000", 0),
        ("-1e-2000000", "-1e-2000000", 0),
    ],
)
def test_range_without_a_grid_point_is_invalid(bottom, top, decimals):
    with pytest.raises(ValidationError):
        NumberRange.create(bottom, top, decimals)


def test_draw_can_reach_each_point_on_a_decimal_grid(monkeypatch):
    number_range = NumberRange.create("-0.025", "0.025", 2)
    offsets = iter(range(5))
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda stop: next(offsets))

    values = [number_range.draw() for _ in range(5)]

    assert values == [-0.02, -0.01, 0, 0.01, 0.02]
    assert all(
        Decimal(str(value)) * 100 == (Decimal(str(value)) * 100).to_integral_value()
        for value in values
    )


def test_full_integer_range_uses_the_complete_crypto_draw_width(monkeypatch):
    width = 2 * MAX_SAFE_INTEGER + 1
    calls = []
    offsets = iter((0, width - 1))

    def draw_offset(stop):
        calls.append(stop)
        return next(offsets)

    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", draw_offset)
    number_range = NumberRange.create(-MAX_SAFE_INTEGER, MAX_SAFE_INTEGER, 0)

    assert number_range.draw() == -MAX_SAFE_INTEGER
    assert number_range.draw() == MAX_SAFE_INTEGER
    assert calls == [width, width]


@pytest.mark.parametrize(
    ("bottom", "top", "decimals"),
    [
        (-MAX_SAFE_INTEGER - 1, 0, 0),
        (0, MAX_SAFE_INTEGER + 1, 0),
        (0, MAX_SAFE_INTEGER, 1),
        (-MAX_SAFE_INTEGER, 0, 1),
        (0, "100000000000000.1", 1),
        ("-100000000000000.1", 0, 1),
        (0, "1000000.000000001", 9),
    ],
)
def test_range_rejects_unsafe_integer_or_decimal_bounds(bottom, top, decimals):
    with pytest.raises(ValidationError):
        NumberRange.create(bottom, top, decimals)


@pytest.mark.parametrize("decimals", [1, 2, 6, 9])
def test_decimal_grid_points_remain_distinct_at_the_safe_limit(monkeypatch, decimals):
    top = Decimal(10**15).scaleb(-decimals)
    bottom = Decimal(10**15 - 2).scaleb(-decimals)
    offsets = iter(range(3))
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda stop: next(offsets))
    number_range = NumberRange.create(bottom, top, decimals)

    values = [number_range.draw() for _ in range(3)]

    assert len(set(values)) == 3
    assert [Decimal(str(value)) for value in values] == [
        Decimal(10**15 - 2 + offset).scaleb(-decimals) for offset in range(3)
    ]


@pytest.mark.parametrize(
    ("value", "expected", "expected_type"),
    [
        (Decimal("0"), 0, int),
        (Decimal("-123.000"), -123, int),
        (Decimal("1.25"), 1.25, float),
        (Decimal("0.000000001"), 0.000000001, float),
    ],
)
def test_native_number_preserves_value_and_uses_integers_where_possible(
    value, expected, expected_type
):
    actual = native_number(value)
    assert actual == expected
    assert type(actual) is expected_type


@pytest.mark.parametrize("value", ["0.12345678901234567890123456789", "1e-1000"])
def test_native_number_rejects_loss_of_precision(value):
    with pytest.raises(ValidationError):
        native_number(Decimal(value))


def test_range_does_not_depend_on_the_callers_decimal_context(monkeypatch):
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda stop: 0)

    with localcontext() as context:
        context.prec = 6
        context.Emax = 6
        context.Emin = -6
        number_range = NumberRange.create("1234567.89", "1234567.89", 2)
        value = number_range.draw()

    assert value == 1234567.89


def test_parse_safe_boundary_does_not_depend_on_the_callers_decimal_precision():
    with localcontext() as context:
        context.prec = 6
        assert parse_number(MAX_SAFE_INTEGER) == Decimal(MAX_SAFE_INTEGER)
        with pytest.raises(ValidationError):
            parse_number(MAX_SAFE_INTEGER + 1)
