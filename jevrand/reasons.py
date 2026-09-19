"""Jev's grounds for objection, not statistical tests of randomness."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RejectionReason:
    code: str
    label: str
    description: str
    examples: tuple[str, ...]


REJECTION_REASONS: tuple[RejectionReason, ...] = (
    RejectionReason(
        code="too_famous",
        label="Too famous",
        description=(
            "Has a specific, widely known claim to fame, such as "
            "42 in The Hitchhiker's Guide to the Galaxy or Ramanujan's 1729."
        ),
        examples=("42", "1729"),
    ),
    RejectionReason(
        code="suspiciously_round",
        label="Suspiciously round",
        description=(
            "Ends in enough zeros to look like a deliberate estimate at this "
            "range. A lone trailing zero is weak evidence."
        ),
        examples=("1000", "5000", "10000"),
    ),
    RejectionReason(
        code="meme",
        label="Meme",
        description=(
            "Is an established internet joke or reference, such as 69, "
            "420, or leetspeak's 1337. The reference must match the actual value."
        ),
        examples=("69", "420", "1337"),
    ),
    RejectionReason(
        code="counting_practice",
        label="Looks like counting practice",
        description=(
            "Has at least four consecutive digits in an obvious ascending or descending sequence."
        ),
        examples=("1234", "9876"),
    ),
    RejectionReason(
        code="stuck_key",
        label="Looks like a stuck key",
        description=(
            "Repeats the same digit at least four times in succession. "
            "One or two matching digits do not make a stuck keyboard."
        ),
        examples=("1111", "7777"),
    ),
    RejectionReason(
        code="copy_paste",
        label="Suspicious use of copy and paste",
        description=(
            "Repeats a block of two or more digits at least twice across the whole number."
        ),
        examples=("1212", "454545"),
    ),
    RejectionReason(
        code="palindrome",
        label="Too pleased with its own reflection",
        description=(
            "Reads the same forwards and backwards across at least four "
            "digits, without invented zero padding."
        ),
        examples=("1221", "45654"),
    ),
    RejectionReason(
        code="borrowed_constant",
        label="Borrowed from a maths textbook",
        description=(
            "Matches a recognisable constant to at least four decimal "
            "places. A vague resemblance is insufficient."
        ),
        examples=("3.14159", "2.71828"),
    ),
    RejectionReason(
        code="computer_default",
        label="Looks like a default buffer size",
        description=(
            "Is a familiar computing capacity such as 1024 or 65536. "
            "A power of two without a familiar computing use is insufficient."
        ),
        examples=("1024", "2048", "65536"),
    ),
    RejectionReason(
        code="retail_price",
        label="Looks like it is on sale",
        description=(
            "Has a familiar retail price form with two decimal places, "
            "such as 19.99. The price cue must occur in the actual value."
        ),
        examples=("9.99", "19.99", "99.95"),
    ),
    RejectionReason(
        code="calendar_entry",
        label="Looks like a calendar entry",
        description=(
            "Spells a complete, valid date in YYYYMMDD form, with no "
            "extra separators or rearrangement of digits."
        ),
        examples=("20240229", "19991231"),
    ),
    RejectionReason(
        code="http_error",
        label="Looks like an HTTP error",
        description=(
            "Matches a conspicuous HTTP error code, such as 404 Not Found "
            "or 418 I'm a teapot. An arbitrary three-digit number is insufficient."
        ),
        examples=("404", "418"),
    ),
)
