from collections.abc import Callable, Iterator
from dataclasses import replace

from .errors import AttemptsExhaustedError, ValidationError
from .models import Result
from .numbers import NumberInput, NumberRange, native_number, parse_number
from .providers import Provider
from .reasons import REJECTION_REASONS

_REASONS = {reason.code: reason for reason in REJECTION_REASONS}


def _question() -> dict:
    return {
        "type": "choice",
        "instructions": (
            "Judge this candidate for a deliberately silly random-number approval service. "
            "A single value cannot prove or disprove randomness; this is a taste judgement. "
            "Choose approved unless there is a clear, specific match to one rejection category. "
            "If several fit, choose the strongest. Do not invent obscure associations. "
            "Being odd, even, prime, positive, negative, or near a bound "
            "is not a reason to reject. "
            "Judge the whole value, not arbitrary substrings. Ignore the sign for digit patterns; "
            "do not invent leading or trailing zeros. Treat criteria examples as illustrations, "
            "not an exhaustive blacklist. The range and decimal places are context only."
        ),
        "criteria": {
            "approved": "No clear objection applies. This number is acceptably unremarkable.",
            **{
                reason.code: (
                    f"{reason.label}: {reason.description} Examples: {', '.join(reason.examples)}."
                )
                for reason in REJECTION_REASONS
            },
        },
    }


class Jevrand:
    def __init__(
        self,
        *,
        provider: str | None = None,
        api_key: str | None = None,
        timeout: float = 30,
    ) -> None:
        self._provider = Provider.configure(provider, api_key, timeout)

    @property
    def provider(self) -> str:
        return self._provider.name

    @property
    def model(self) -> str:
        return self._provider.model

    def _judge(self, number: int | float, number_range: NumberRange | None = None) -> Result:
        state: dict = {"number": number}
        if number_range is not None:
            state["range"] = number_range.describe()
        choice = self._provider.decide(state, _question())
        approved = choice == "approved"
        reason = _REASONS.get(choice)
        return Result(
            number=number,
            approved=approved,
            reasons=() if approved else (choice,),
            explanation="Jev has no objection." if approved else reason.label,
            provider=self.provider,
            model=self.model,
        )

    def check(self, number: NumberInput) -> Result:
        return self._judge(native_number(parse_number(number)))

    def generate(
        self,
        top: NumberInput = 10000,
        *,
        bottom: NumberInput = 0,
        decimals: int = 0,
        max_attempts: int | None = None,
        on_verdict: Callable[[Result], None] | None = None,
    ) -> Result:
        return next(
            self.generate_many(
                1,
                top,
                bottom=bottom,
                decimals=decimals,
                max_attempts=max_attempts,
                on_verdict=on_verdict,
            )
        )

    def generate_many(
        self,
        count: int,
        top: NumberInput = 10000,
        *,
        bottom: NumberInput = 0,
        decimals: int = 0,
        max_attempts: int | None = None,
        on_verdict: Callable[[Result], None] | None = None,
    ) -> Iterator[Result]:
        if type(count) is not int or count < 1:
            raise ValidationError("The count must be a positive integer.")
        number_range = NumberRange.create(bottom, top, decimals)
        if max_attempts is not None and (type(max_attempts) is not int or max_attempts < 1):
            raise ValidationError("The attempt limit must be a positive integer.")
        if max_attempts is not None and max_attempts < count:
            raise ValidationError("The attempt limit must be at least the requested count.")
        if on_verdict is not None and not callable(on_verdict):
            raise ValidationError("The verdict callback must be callable.")
        attempts = 0
        approved = 0
        while approved < count:
            attempts += 1
            result = replace(self._judge(number_range.draw(), number_range), attempts=attempts)
            if on_verdict is not None:
                on_verdict(result)
            if result.approved:
                approved += 1
                yield result
            if approved < count and max_attempts is not None and attempts >= max_attempts:
                raise AttemptsExhaustedError(attempts, result, requested=count, approved=approved)
