from abc import ABC, abstractmethod
from pathlib import Path
from analysis.services.types import NormalizedFinding


class Analyzer(ABC):
    tool_name: str

    @abstractmethod
    def analyze(self, source_dir: Path, workspace_dir: Path) -> list[NormalizedFinding]:
        raise NotImplementedError
