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
        description="Generate random numbers until Jev approves one, or check a number.",
        epilog=(
            "Examples: jevrand | jevrand 100 | jevrand -10 10 --decimals 2 | "
            "jevrand check 42 --json | jevrand reasons"
        ),
    )
    parser._negative_number_matcher = re.compile(r"^-\d*\.?\d+(?:[eE][+-]?\d+)?$")
    parser.add_argument(
        "values", nargs="*", metavar="VALUE", help="[TOP], [BOTTOM TOP], check NUMBER, or reasons"
    )
    parser.add_argument(
        "--decimals",
        nargs="?",
        type=int,
        const=2,
        metavar="N",
        help="decimal places from 0 to 9 (2 if N is omitted; integers by default)",
    )
    parser.add_argument("--json", action="store_true", help="print one JSON result or error")
    parser.add_argument("--verbose", action="store_true", help="print each verdict to stderr")
    parser.add_argument(
        "--max-attempts", type=int, metavar="N", help="stop after N rejected candidates"
    )
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


def _verdict_text(result: Result) -> str:
    decision = "approved" if result.approved else "rejected"
    return f"{result.number}: {decision}. {result.explanation}"


def _report(result: Result) -> None:
    print(f"[{result.attempts}] {_verdict_text(result)}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    arguments = sys.argv[1:] if argv is None else argv
    json_output = "--json" in arguments
    try:
        args = _parser().parse_intermixed_args(arguments)
        values = args.values
        command = values.pop(0) if values and values[0] in ("check", "reasons") else "generate"
        if command != "generate" and (args.decimals is not None or args.max_attempts is not None):
            raise ValidationError("--decimals and --max-attempts apply only to generation.")
        if command == "reasons":
            if values:
                raise ValidationError("The reasons command does not take a number.")
            if args.json:
                print(json.dumps([asdict(reason) for reason in REJECTION_REASONS]))
            else:
                for reason in REJECTION_REASONS:
                    print(f"{reason.code}: {reason.label}\n  {reason.description}")
            return 0
        if command == "check":
            if len(values) != 1:
                raise ValidationError("Use jevrand check NUMBER.")
            number = native_number(parse_number(values[0]))
        else:
            if len(values) > 2:
                raise ValidationError("Supply no bounds, TOP, or BOTTOM TOP.")
            bottom, top = values if len(values) == 2 else (0, values[0] if values else 10000)
            decimals = 0 if args.decimals is None else args.decimals
            NumberRange.create(bottom, top, decimals)
            if args.max_attempts is not None and args.max_attempts < 1:
                raise ValidationError("The attempt limit must be a positive integer.")
        client = Jevrand(provider=args.provider, timeout=args.timeout)
        if command == "check":
            result = client.check(number)
        else:
            result = client.generate(
                top=top,
                bottom=bottom,
                decimals=decimals,
                max_attempts=args.max_attempts,
                on_verdict=_report if args.verbose else None,
            )
        if args.json:
            print(result.to_json())
        elif command == "check":
            print(_verdict_text(result))
        else:
            print(format(result.number, f".{decimals}f") if decimals else result.number)
        return 0 if result.approved else 1
    except JevrandError as exc:
        if json_output:
            print(json.dumps({"error": {"code": exc.code, "message": str(exc)}}))
        else:
            print(f"jevrand: {exc}", file=sys.stderr)
        return 1 if isinstance(exc, AttemptsExhaustedError) else 2
    except KeyboardInterrupt:
        if json_output:
            print(json.dumps({"error": {"code": "interrupted", "message": "Stopped by the user."}}))
        else:
            print("jevrand: stopped by the user.", file=sys.stderr)
        return 130
