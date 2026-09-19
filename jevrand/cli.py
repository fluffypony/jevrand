import argparse
import json
import re
import sys
from dataclasses import asdict

from . import REJECTION_REASONS, Jevrand, Result, __version__
from .errors import AttemptsExhaustedError, JevrandError, ValidationError
from .numbers import NumberRange, native_number, parse_number


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise ValidationError(message)


def _parser() -> argparse.ArgumentParser:
    parser = _Parser(
        prog="jevrand",
        allow_abbrev=False,
        usage=(
            "jevrand [NUMBER] [options]\n       jevrand --range TOP [options]\n"
            "       jevrand --range BOTTOM TOP [options]\n       jevrand reasons [--json]"
        ),
        description=(
            "Supply NUMBER to check it once. With no NUMBER, generate candidates until Jev "
            "approves one. Every candidate and verdict is shown."
        ),
        epilog=(
            "Examples: jevrand 8008 | jevrand | jevrand --range 100 | "
            "jevrand --range -10 10 --decimals 2 | jevrand 42 --json"
        ),
    )
    parser._negative_number_matcher = re.compile(r"^-\d*\.?\d+(?:[eE][+-]?\d+)?$")
    parser.add_argument(
        "number",
        nargs="?",
        metavar="NUMBER",
        help="check this number once; use reasons for the catalogue",
    )
    parser.add_argument(
        "--range",
        nargs="+",
        dest="bounds",
        metavar="BOUND",
        help="generate in 0..TOP or BOTTOM..TOP, inclusive (default: 0..10000)",
    )
    parser.add_argument(
        "--decimals",
        nargs="?",
        type=int,
        const=2,
        metavar="N",
        help="decimal places from 0 to 9 (2 if N is omitted; integers by default)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one JSON object per verdict; generation uses JSON Lines",
    )
    parser.add_argument("--max-attempts", type=int, metavar="N", help="check at most N candidates")
    parser.add_argument(
        "--timeout", type=float, default=30, metavar="SECONDS", help="socket timeout (default: 30)"
    )
    parser.add_argument(
        "--provider",
        choices=("typesafe", "openrouter"),
        help="override automatic provider selection",
    )
    parser.add_argument("--version", action="version", version=f"jevrand {__version__}")
    return parser


def _verdict_text(result: Result, decimals: int | None = None) -> str:
    decision = "approved" if result.approved else "rejected"
    number = str(result.number) if decimals is None else format(result.number, f".{decimals}f")
    return f"{number}: {decision}. {result.explanation}"


def _report(result: Result, *, json_output: bool, decimals: int) -> None:
    output = (
        result.to_json()
        if json_output
        else f"[{result.attempts}] {_verdict_text(result, decimals)}"
    )
    print(output, flush=True)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    json_output = "--json" in arguments
    try:
        args = _parser().parse_intermixed_args(arguments)
        json_output = args.json
        if args.number is not None and any(
            option is not None for option in (args.bounds, args.decimals, args.max_attempts)
        ):
            raise ValidationError(
                "--range, --decimals, and --max-attempts apply only to generation. "
                "Omit NUMBER to generate; supply NUMBER alone to check it."
            )
        if args.number == "reasons":
            if args.json:
                print(json.dumps([asdict(reason) for reason in REJECTION_REASONS]))
            else:
                for reason in REJECTION_REASONS:
                    print(f"{reason.code}: {reason.label}\n  {reason.description}")
            return 0
        if args.number is not None:
            number = native_number(parse_number(args.number))
        else:
            bounds = args.bounds if args.bounds is not None else ["10000"]
            if len(bounds) not in (1, 2):
                raise ValidationError("Use --range TOP or --range BOTTOM TOP.")
            bottom, top = bounds if len(bounds) == 2 else (0, bounds[0])
            decimals = 0 if args.decimals is None else args.decimals
            NumberRange.create(bottom, top, decimals)
            if args.max_attempts is not None and args.max_attempts < 1:
                raise ValidationError("The attempt limit must be a positive integer.")
        client = Jevrand(provider=args.provider, timeout=args.timeout)
        if args.number is not None:
            result = client.check(number)
            print(result.to_json() if args.json else _verdict_text(result), flush=True)
        else:
            result = client.generate(
                top=top,
                bottom=bottom,
                decimals=decimals,
                max_attempts=args.max_attempts,
                on_verdict=lambda verdict: _report(
                    verdict, json_output=args.json, decimals=decimals
                ),
            )
        return 0 if result.approved else 1
    except JevrandError as exc:
        if json_output:
            print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}), flush=True)
        else:
            print(f"jevrand: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, AttemptsExhaustedError) else 2
    except KeyboardInterrupt:
        if json_output:
            print(
                json.dumps({"error": {"code": "interrupted", "message": "Stopped by the user."}}),
                flush=True,
            )
        else:
            print("jevrand: stopped by the user.", file=sys.stderr)
        return 130
