import pytest

from jevrand import Jevrand
from jevrand.numbers import NumberRange


@pytest.fixture
def live_client(request):
    provider = request.config.getoption("--live-provider")
    if provider is None:
        pytest.skip("Select --live-provider to run billable Jev regression tests.")
    return Jevrand(provider=provider)


@pytest.mark.parametrize(
    ("number", "approved"),
    [
        (111, False),
        (222, False),
        (777, False),
        (888, False),
        (999, False),
        (-888, False),
        (8888, False),
        ("888.00", False),
        (738, True),
        (1882, True),
        (883, True),
    ],
)
def test_jev_distinguishes_repeated_digits_from_ordinary_numbers(live_client, number, approved):
    result = live_client.check(number)
    assert result.approved is approved, result.to_json()


def test_generation_rejects_888_and_continues_with_a_new_candidate(live_client, monkeypatch):
    candidates = iter([888, 738])
    monkeypatch.setattr(NumberRange, "draw", lambda self: next(candidates))
    verdicts = []

    result = live_client.generate(max_attempts=2, on_verdict=verdicts.append)

    assert result.number == 738, result.to_json()
    assert result.attempts == 2
    assert verdicts[0].number == 888
    assert verdicts[0].approved is False
