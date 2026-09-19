import json
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Result:
    number: int | float
    approved: bool
    reasons: tuple[str, ...]
    explanation: str
    provider: str
    model: str
    attempts: int = 1

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, allow_nan=False)
