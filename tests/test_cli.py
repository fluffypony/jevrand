import io
import json
import os
import subprocess
import sys

import pytest

from jevrand.cli import main
from jevrand.errors import ProviderError
from jevrand.providers import Provider


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "fake-key")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    def unexpected_call(*args):
        pytest.fail("This command must not call the provider.")

    monkeypatch.setattr(Provider, "decide", unexpected_call)


def decisions(monkeypatch, replies):
    calls = []
    replies = iter(replies)

    def decide(self, state, question):
        calls.append(state)
        reply = next(replies)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    monkeypatch.setattr(Provider, "decide", decide)
    return calls


def json_lines(output):
    return [json.loads(line) for line in output.splitlines()]


@pytest.mark.parametrize(
    ("args", "expected", "bounds"),
    [
        ([], "10000", {"bottom": "0", "top": "10000", "decimals": 0}),
        (["--range", "100"], "100", {"bottom": "0", "top": "100", "decimals": 0}),
        (["--range", "-10", "-2"], "-2", {"bottom": "-10", "top": "-2", "decimals": 0}),
        (
            ["--range", "1", "2", "--decimals", "3"],
            "2.000",
            {"bottom": "1", "top": "2", "decimals": 3},
        ),
        (
            ["--decimals", "--range", "1", "2"],
            "2.00",
            {"bottom": "1", "top": "2", "decimals": 2},
        ),
        (
            ["--range", "-1e2", "-1e1"],
            "-10",
            {"bottom": "-1E+2", "top": "-1E+1", "decimals": 0},
        ),
    ],
)
def test_generate_forms(monkeypatch, capsys, args, expected, bounds):
    calls = decisions(monkeypatch, ["approved"])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: width - 1)
    assert main(args) == 0
    output = capsys.readouterr()
    assert not output.err
    assert output.out == f"[1] {expected}: approved. Jev has no objection.\n"
    assert calls == [{"number": float(expected), "range": bounds}]


@pytest.mark.parametrize("json_output", [False, True])
def test_generation_reports_every_candidate_once_in_order(monkeypatch, capsys, json_output):
    calls = decisions(monkeypatch, ["stuck_key", "too_famous", "approved"])
    ticks = iter([888, 42, 738])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))
    assert main(["--json"] if json_output else []) == 0
    output = capsys.readouterr()
    assert not output.err
    assert [call["number"] for call in calls] == [888, 42, 738]
    if json_output:
        results = json_lines(output.out)
        assert [result["number"] for result in results] == [888, 42, 738]
        assert [result["attempts"] for result in results] == [1, 2, 3]
        assert [result["approved"] for result in results] == [False, False, True]
        assert [result["reasons"] for result in results] == [["stuck_key"], ["too_famous"], []]
        assert [result["explanation"] for result in results] == [
            "Looks like a stuck key",
            "Too famous",
            "Jev has no objection.",
        ]
    else:
        assert output.out.splitlines() == [
            "[1] 888: rejected. Looks like a stuck key",
            "[2] 42: rejected. Too famous",
            "[3] 738: approved. Jev has no objection.",
        ]


@pytest.mark.parametrize("json_output", [False, True])
def test_count_generates_requested_approvals_and_reports_every_verdict(
    monkeypatch, capsys, json_output
):
    calls = decisions(monkeypatch, ["stuck_key", "approved", "too_famous", "approved"])
    ticks = iter([888, 738, 42, 853])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))
    args = ["--count", "2"]
    assert main([*args, "--json"] if json_output else args) == 0
    output = capsys.readouterr()

    assert not output.err
    assert [call["number"] for call in calls] == [888, 738, 42, 853]
    if json_output:
        results = json_lines(output.out)
        assert [result["number"] for result in results] == [888, 738, 42, 853]
        assert [result["attempts"] for result in results] == [1, 2, 3, 4]
        assert [result["approved"] for result in results] == [False, True, False, True]
        assert [result["reasons"] for result in results] == [["stuck_key"], [], ["too_famous"], []]
    else:
        assert output.out.splitlines() == [
            "[1] 888: rejected. Looks like a stuck key",
            "[2] 738: approved. Jev has no objection.",
            "[3] 42: rejected. Too famous",
            "[4] 853: approved. Jev has no objection.",
        ]


def test_count_one_hundred_outputs_one_hundred_approvals(monkeypatch, capsys):
    calls = decisions(monkeypatch, ["approved"] * 100)
    assert main(["--count", "100", "--json"]) == 0
    output = capsys.readouterr()
    results = json_lines(output.out)

    assert not output.err
    assert len(results) == 100
    assert len(calls) == 100
    assert all(result["approved"] for result in results)
    assert [result["attempts"] for result in results] == list(range(1, 101))


def test_count_preserves_range_decimal_format_and_repeated_approvals(monkeypatch, capsys):
    calls = decisions(monkeypatch, ["approved", "approved"])
    assert main(["--count", "2", "--range", "0.73", "0.73", "--decimals", "3"]) == 0
    output = capsys.readouterr()

    assert not output.err
    assert output.out.splitlines() == [
        "[1] 0.730: approved. Jev has no objection.",
        "[2] 0.730: approved. Jev has no objection.",
    ]
    assert len(calls) == 2
    assert all(call["range"] == {"bottom": "0.73", "top": "0.73", "decimals": 3} for call in calls)


@pytest.mark.parametrize("json_output", [False, True])
def test_count_partial_exhaustion_retains_approvals_and_rejections(
    monkeypatch, capsys, json_output
):
    calls = decisions(monkeypatch, ["approved", "too_famous", "approved"])
    args = ["--count", "2", "--range", "42", "42", "--max-attempts", "2"]
    assert main([*args, "--json"] if json_output else args) == 1
    output = capsys.readouterr()

    assert len(calls) == 2
    if json_output:
        assert not output.err
        results = json_lines(output.out)
        assert len(results) == 3
        assert [result["approved"] for result in results[:-1]] == [True, False]
        assert [result["attempts"] for result in results[:-1]] == [1, 2]
        assert results[-1]["error"]["code"] == "attempts_exhausted"
    else:
        assert output.out.splitlines() == [
            "[1] 42: approved. Jev has no objection.",
            "[2] 42: rejected. Too famous",
        ]
        assert output.err.startswith("jevrand: ")


def test_count_final_approval_can_use_last_allowed_attempt(monkeypatch, capsys):
    calls = decisions(monkeypatch, ["approved", "meme", "approved"])
    assert main(["--count", "2", "--max-attempts", "3", "--json"]) == 0
    output = capsys.readouterr()

    assert not output.err
    assert len(calls) == 3
    assert [result["approved"] for result in json_lines(output.out)] == [True, False, True]


@pytest.mark.parametrize("json_output", [False, True])
def test_count_provider_failure_preserves_prior_approval(monkeypatch, capsys, json_output):
    calls = decisions(monkeypatch, ["approved", ProviderError("offline"), "approved"])
    args = ["--count", "2", "--range", "731", "731"]
    assert main([*args, "--json"] if json_output else args) == 2
    output = capsys.readouterr()

    assert len(calls) == 2
    if json_output:
        assert not output.err
        results = json_lines(output.out)
        assert len(results) == 2
        assert results[0]["number"] == 731
        assert results[0]["approved"] is True
        assert results[-1]["error"]["code"] == "provider_error"
    else:
        assert output.out == "[1] 731: approved. Jev has no objection.\n"
        assert output.err.startswith("jevrand: ")


def test_generation_formats_decimal_places_on_every_verdict(monkeypatch, capsys):
    decisions(monkeypatch, ["retail_price", "approved"])
    ticks = iter([9990, 7000])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))
    assert main(["--range", "10", "--decimals", "3"]) == 0
    output = capsys.readouterr()
    assert not output.err
    assert output.out.splitlines() == [
        "[1] 9.990: rejected. Looks like it is on sale",
        "[2] 7.000: approved. Jev has no objection.",
    ]


@pytest.mark.parametrize("json_output", [False, True])
@pytest.mark.parametrize("first_approved", [False, True])
def test_generation_flushes_each_verdict_before_next_call(monkeypatch, json_output, first_approved):
    class Capture(io.StringIO):
        def __init__(self):
            super().__init__()
            self.flushed = []

        def flush(self):
            self.flushed.append(self.getvalue())

    output = Capture()
    monkeypatch.setattr(sys, "stdout", output)
    ticks = iter([42, 731])
    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", lambda width: next(ticks))

    def decide(self, state, question):
        if state["number"] == 42:
            return "approved" if first_approved else "too_famous"
        assert output.flushed
        if json_output:
            assert json_lines(output.flushed[-1])[0]["number"] == 42
        else:
            expected = (
                "approved. Jev has no objection." if first_approved else "rejected. Too famous"
            )
            assert output.flushed[-1] == f"[1] 42: {expected}\n"
        return "approved"

    monkeypatch.setattr(Provider, "decide", decide)
    args = ["--count", "2"] if first_approved else []
    assert main([*args, "--json"] if json_output else args) == 0


@pytest.mark.parametrize("json_output", [False, True])
def test_positional_number_checks_once_and_never_draws(monkeypatch, capsys, json_output):
    calls = decisions(monkeypatch, ["palindrome"])

    def unexpected_draw(width):
        pytest.fail("Checking a number must not generate a replacement.")

    monkeypatch.setattr("jevrand.numbers.secrets.randbelow", unexpected_draw)
    args = ["8008", "--json"] if json_output else ["8008"]
    assert main(args) == 1
    output = capsys.readouterr()
    assert not output.err
    assert calls == [{"number": 8008}]
    if json_output:
        assert json.loads(output.out) == {
            "number": 8008,
            "approved": False,
            "reasons": ["palindrome"],
            "explanation": "Too pleased with its own reflection",
            "provider": "typesafe",
            "model": "jev-latest",
            "attempts": 1,
        }
    else:
        assert output.out == "8008: rejected. Too pleased with its own reflection\n"


@pytest.mark.parametrize(
    ("value", "number"),
    [("0", 0), ("738", 738), ("1e2", 100), ("-1e2", -100), ("1.25", 1.25), ("-.5", -0.5)],
)
def test_approved_number_check(monkeypatch, capsys, value, number):
    calls = decisions(monkeypatch, ["approved"])
    assert main([value]) == 0
    output = capsys.readouterr()
    assert not output.err
    assert output.out == f"{number}: approved. Jev has no objection.\n"
    assert calls == [{"number": number}]


@pytest.mark.parametrize(
    "args",
    [
        ["check"],
        ["check", "42"],
        ["--verbose"],
        ["--j"],
        ["reasons", "1"],
        ["reasons", "--range", "100"],
        ["reasons", "--decimals"],
        ["reasons", "--max-attempts", "1"],
        ["1", "2"],
        ["--range"],
        ["--range", "1", "2", "3"],
        ["--range", "10", "0"],
        ["--range", "NaN"],
        ["--no-such-flag"],
        ["--decimals", "10"],
        ["--max-attempts", "0"],
        ["NaN"],
        ["42", "--range", "100"],
        ["--range", "100", "--json", "42"],
        ["42", "--decimals"],
        ["42", "--decimals", "0"],
        ["42", "--max-attempts", "5"],
        ["--count"],
        ["--count", "0"],
        ["--count", "-1"],
        ["--count", "1.5"],
        ["--count", "NaN"],
        ["--count", "2", "--max-attempts", "1"],
        ["42", "--count", "1"],
        ["42", "--count", "2"],
        ["reasons", "--count", "1"],
        ["reasons", "--count", "2"],
    ],
)
def test_invalid_input_has_json_error(args, capsys):
    assert main([*args, "--json"]) == 2
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["error"]["code"] == "invalid_input"


@pytest.mark.parametrize("json_output", [False, True])
def test_exhaustion_retains_all_rejections(monkeypatch, capsys, json_output):
    decisions(monkeypatch, ["too_famous", "too_famous"])
    args = ["--range", "42", "42", "--max-attempts", "2"]
    assert main([*args, "--json"] if json_output else args) == 1
    output = capsys.readouterr()
    if json_output:
        assert not output.err
        results = json_lines(output.out)
        assert len(results) == 3
        assert [result["number"] for result in results[:-1]] == [42, 42]
        assert [result["attempts"] for result in results[:-1]] == [1, 2]
        assert all(result["approved"] is False for result in results[:-1])
        assert results[-1]["error"]["code"] == "attempts_exhausted"
    else:
        assert output.out.splitlines() == [
            "[1] 42: rejected. Too famous",
            "[2] 42: rejected. Too famous",
        ]
        assert output.err.startswith("jevrand: ")


@pytest.mark.parametrize(
    ("failure", "status", "code"),
    [(ProviderError("offline"), 2, "provider_error"), (KeyboardInterrupt(), 130, "interrupted")],
)
@pytest.mark.parametrize("prior_rejection", [False, True])
@pytest.mark.parametrize("json_output", [False, True])
def test_generation_failure_retains_prior_verdicts(
    monkeypatch, capsys, failure, status, code, prior_rejection, json_output
):
    decisions(monkeypatch, ["too_famous", failure] if prior_rejection else [failure])
    args = ["--range", "42", "42"]
    assert main([*args, "--json"] if json_output else args) == status
    output = capsys.readouterr()
    if json_output:
        assert not output.err
        results = json_lines(output.out)
        assert len(results) == (2 if prior_rejection else 1)
        assert results[-1]["error"]["code"] == code
        if prior_rejection:
            assert results[0]["number"] == 42
            assert results[0]["reasons"] == ["too_famous"]
    else:
        assert output.out == ("[1] 42: rejected. Too famous\n" if prior_rejection else "")
        assert output.err.startswith("jevrand: ")


def test_invalid_human_input_uses_stderr(capsys):
    assert main(["42", "--range", "100"]) == 2
    output = capsys.readouterr()
    assert not output.out
    assert output.err.startswith("jevrand: ")


def test_help_explains_checks_and_explicit_range(capsys):
    with pytest.raises(SystemExit) as caught:
        main(["--help"])
    assert caught.value.code == 0
    output = capsys.readouterr()
    assert not output.err
    assert "--range" in output.out
    assert "--count" in output.out
    assert "NUMBER" in output.out
    assert "BOTTOM" in output.out
    assert "TOP" in output.out
    assert "jevrand check" not in " ".join(output.out.split())
    assert "--verbose" not in output.out


@pytest.mark.parametrize("args", [["--help"], ["--version"], ["reasons"], ["reasons", "--json"]])
def test_offline_commands_in_fresh_process(args):
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in (
            "TYPESAFE_API_KEY",
            "OPENROUTER_API_KEY",
        )
    }
    completed = subprocess.run(
        [sys.executable, "-m", "jevrand", *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout
    assert not completed.stderr


def test_missing_credentials(monkeypatch, capsys):
    monkeypatch.delenv("TYPESAFE_API_KEY")
    assert main(["--json"]) == 2
    output = capsys.readouterr()
    assert not output.err
    assert json.loads(output.out)["error"]["code"] == "configuration_error"
