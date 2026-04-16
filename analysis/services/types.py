from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedFinding:
    tool: str
    severity: str
    rule: str
    file_path: str
    line: int | None
    message: str
