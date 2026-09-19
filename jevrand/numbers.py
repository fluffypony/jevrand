import math
import secrets
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Context, Decimal, InvalidOperation, localcontext

from .errors import ValidationError

MAX_SAFE_INTEGER = 2**53 - 1
MAX_DECIMALS = 9
NumberInput = int | float | str | Decimal


def parse_number(value: NumberInput) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValidationError("Supply a finite number.")
    if isinstance(value, int) and abs(value) > MAX_SAFE_INTEGER:
        raise ValidationError(f"Numbers must be within +/-{MAX_SAFE_INTEGER}.")
    # Bound input size before Decimal can allocate or format an enormous value.
    text = str(value).strip()
    if not text or len(text) > 100:
        raise ValidationError("Supply a number with at most 100 characters.")
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValidationError("Supply a finite number.") from exc
    if not number.is_finite() or number.copy_abs() > MAX_SAFE_INTEGER:
        raise ValidationError(f"Numbers must be finite and within +/-{MAX_SAFE_INTEGER}.")
    if not number:
        return Decimal(0)
    if number.adjusted() < -100:
        raise ValidationError("Numbers must be at least 1e-100 in magnitude, or zero.")
    return number


def native_number(number: Decimal) -> int | float:
    if number == number.to_integral_value():
        return int(number)
    value = float(number)
    if not math.isfinite(value) or Decimal(str(value)) != number:
        raise ValidationError("The number cannot be represented without a loss of precision.")
    return value


@dataclass(frozen=True)
class NumberRange:
    bottom: Decimal
    top: Decimal
    decimals: int
    first: int
    last: int

    @classmethod
    def create(cls, bottom: NumberInput, top: NumberInput, decimals: int) -> "NumberRange":
        if type(decimals) is not int or not 0 <= decimals <= MAX_DECIMALS:
            raise ValidationError(f"Decimal places must be an integer from 0 to {MAX_DECIMALS}.")
        low, high = parse_number(bottom), parse_number(top)
        if low > high:
            raise ValidationError("The bottom of the range must not exceed the top.")
        # Bounds can contain more digits than the process-wide Decimal context.
        with localcontext(Context(prec=120)):
            scaled_low, scaled_high = low.scaleb(decimals), high.scaleb(decimals)
            if max(abs(scaled_low), abs(scaled_high)) > MAX_SAFE_INTEGER:
                raise ValidationError("The range is too large for the requested decimal places.")
            first = int(scaled_low.to_integral_value(rounding=ROUND_CEILING))
            last = int(scaled_high.to_integral_value(rounding=ROUND_FLOOR))
        if first > last:
            raise ValidationError("The range contains no numbers at the requested decimal places.")
        # A conservative float limit keeps every decimal grid point distinct.
        if decimals and max(abs(first), abs(last)) > 10**15:
            raise ValidationError("Decimal ranges must fit within 15 significant digits.")
        return cls(low, high, decimals, first, last)

    def draw(self) -> int | float:
        tick = self.first + secrets.randbelow(self.last - self.first + 1)
        with localcontext(Context(prec=120)):
            return native_number(Decimal(tick).scaleb(-self.decimals))

    def describe(self) -> dict[str, str | int]:
        return {"bottom": str(self.bottom), "top": str(self.top), "decimals": self.decimals}
