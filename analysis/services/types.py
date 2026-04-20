from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedFinding:
    tool: str
    severity: str
    rule: str
    issue_key: str
    issue_status: str
    file_path: str
    line: int | None
    message: str
    finding_type: str = ''
    effort_minutes: int | None = None


@dataclass(frozen=True)
class SonarMetrics:
    quality_gate_status: str
    bugs: int
    vulnerabilities: int
    code_smells: int
    complexity: int
    duplicated_lines_density: float
    duplicated_lines: int
    coverage: float
    lines_to_cover: int
    ncloc: int
    reliability_rating: int
    security_rating: int
    maintainability_rating: int


@dataclass(frozen=True)
class SonarAnalysisResult:
    findings: list[NormalizedFinding]
    metrics: SonarMetrics
