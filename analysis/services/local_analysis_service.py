from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import javalang
import lizard
from django.conf import settings

from analysis.services.java_syntax_metrics import JavaSyntaxMetricsResult, extract_java_syntax_metrics
from analysis.services.types import NormalizedFinding


@dataclass(frozen=True)
class LocalAnalysisMetrics:
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
class LocalAnalysisResult:
    findings: list[NormalizedFinding]
    syntax_metrics: JavaSyntaxMetricsResult
    metrics: LocalAnalysisMetrics


def run_local_analysis(source_dir: Path, workspace_dir: Path) -> LocalAnalysisResult:
    syntax_metrics = extract_java_syntax_metrics(source_dir)
    pmd_findings = _run_pmd(source_dir)
    spotbugs_findings = _run_spotbugs(source_dir, workspace_dir)
    semgrep_findings = _run_semgrep(source_dir)
    custom_findings, lizard_summary = _collect_custom_metrics(source_dir)

    all_findings = pmd_findings + spotbugs_findings + semgrep_findings + custom_findings
    all_findings = _dedupe_findings(all_findings)

    metrics = _build_metrics(all_findings, lizard_summary)
    return LocalAnalysisResult(findings=all_findings, syntax_metrics=syntax_metrics, metrics=metrics)


def _iter_java_files(source_dir: Path) -> list[Path]:
    root = source_dir.resolve()
    out: list[Path] = []
    for path in sorted(source_dir.rglob("*.java")):
        rel = path.resolve().relative_to(root)
        rel_posix = PurePosixPath(rel.as_posix())
        if "__MACOSX" in rel_posix.parts:
            continue
        if rel_posix.name.startswith("._"):
            continue
        out.append(path)
    return out


def _run_pmd(source_dir: Path) -> list[NormalizedFinding]:
    command = str(getattr(settings, "ANALYSIS_PMD_COMMAND", "pmd")).strip()
    if not command or shutil.which(command) is None:
        return []
    rules = str(
        getattr(
            settings,
            "ANALYSIS_PMD_RULESETS",
            "category/java/bestpractices.xml,category/java/errorprone.xml,category/java/design.xml",
        )
    ).strip()
    timeout = int(getattr(settings, "ANALYSIS_TOOL_TIMEOUT_SECONDS", 120))
    proc = subprocess.run(
        [command, "check", "-d", str(source_dir), "-R", rules, "-f", "json"],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    findings: list[NormalizedFinding] = []
    for item in data.get("files", []) or []:
        file_path = str(item.get("filename") or "")
        for violation in item.get("violations", []) or []:
            severity = _map_pmd_priority_to_severity(violation.get("priority"))
            rule = str(violation.get("rule") or "pmd:unknown")
            begin_line = violation.get("beginline")
            message = str(violation.get("description") or "Violación PMD")
            issue_key = _stable_issue_key("pmd", rule, file_path, begin_line, message)
            findings.append(
                NormalizedFinding(
                    tool="pmd",
                    severity=severity,
                    rule=rule,
                    issue_key=issue_key,
                    issue_status="OPEN",
                    file_path=file_path,
                    line=int(begin_line) if begin_line else None,
                    message=message,
                    finding_type="CODE_SMELL",
                    effort_minutes=None,
                )
            )
    return findings


def _run_spotbugs(source_dir: Path, workspace_dir: Path) -> list[NormalizedFinding]:
    command = str(getattr(settings, "ANALYSIS_SPOTBUGS_COMMAND", "spotbugs")).strip()
    if not command or shutil.which(command.split()[0]) is None:
        return []
    output_path = workspace_dir / "spotbugs.xml"
    timeout = int(getattr(settings, "ANALYSIS_TOOL_TIMEOUT_SECONDS", 120))
    proc = subprocess.run(
        command.split() + ["-textui", "-xml:withMessages", "-output", str(output_path), str(source_dir)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode not in (0, 1) or not output_path.exists():
        return []
    if output_path.stat().st_size == 0:
        return []
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(output_path)
    except ET.ParseError:
        return []
    root = tree.getroot()
    findings: list[NormalizedFinding] = []
    for bug in root.findall(".//BugInstance"):
        bug_type = str(bug.attrib.get("type", "spotbugs:unknown"))
        priority = int(bug.attrib.get("priority", "3"))
        severity = _map_spotbugs_priority_to_severity(priority)
        category = str(bug.attrib.get("category", "BUG"))
        source_line = bug.find(".//SourceLine")
        file_path = str(source_line.attrib.get("sourcepath", "")) if source_line is not None else ""
        line = int(source_line.attrib.get("start")) if source_line is not None and source_line.attrib.get("start") else None
        long_message_node = bug.find("LongMessage")
        message = long_message_node.text.strip() if long_message_node is not None and long_message_node.text else bug_type
        issue_key = _stable_issue_key("spotbugs", bug_type, file_path, line, message)
        findings.append(
            NormalizedFinding(
                tool="spotbugs",
                severity=severity,
                rule=bug_type,
                issue_key=issue_key,
                issue_status="OPEN",
                file_path=file_path,
                line=line,
                message=message,
                finding_type="BUG" if category.upper() in {"CORRECTNESS", "BAD_PRACTICE"} else "CODE_SMELL",
                effort_minutes=None,
            )
        )
    return findings


def _run_semgrep(source_dir: Path) -> list[NormalizedFinding]:
    command = str(getattr(settings, "ANALYSIS_SEMGREP_COMMAND", "semgrep")).strip()
    if not command or shutil.which(command) is None:
        return []
    timeout = int(getattr(settings, "ANALYSIS_TOOL_TIMEOUT_SECONDS", 120))
    proc = subprocess.run(
        [command, "--config", "auto", "--json", str(source_dir)],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    findings: list[NormalizedFinding] = []
    for item in data.get("results", []) or []:
        extra = item.get("extra") or {}
        line = (item.get("start") or {}).get("line")
        severity = _map_semgrep_severity(str(extra.get("severity") or "INFO"))
        rule = str(item.get("check_id") or "semgrep:unknown")
        message = str(extra.get("message") or "Hallazgo Semgrep")
        file_path = str(item.get("path") or "")
        issue_key = _stable_issue_key("semgrep", rule, file_path, line, message)
        findings.append(
            NormalizedFinding(
                tool="semgrep",
                severity=severity,
                rule=rule,
                issue_key=issue_key,
                issue_status="OPEN",
                file_path=file_path,
                line=int(line) if line else None,
                message=message,
                finding_type="VULNERABILITY" if severity in {"CRITICAL", "HIGH"} else "CODE_SMELL",
                effort_minutes=None,
            )
        )
    return findings


def _collect_custom_metrics(source_dir: Path) -> tuple[list[NormalizedFinding], dict[str, float]]:
    java_files = _iter_java_files(source_dir)
    findings: list[NormalizedFinding] = []
    total_ccn = 0
    total_nloc = 0
    duplicated_methods = 0
    method_fingerprints: dict[str, int] = {}

    for file_path in java_files:
        rel = file_path.relative_to(source_dir).as_posix()
        analysis = lizard.analyze_file(str(file_path))
        total_nloc += int(analysis.nloc or 0)
        for fn in analysis.function_list:
            total_ccn += int(fn.cyclomatic_complexity or 0)
            if int(fn.cyclomatic_complexity or 0) >= 15:
                findings.append(_metric_finding("lizard", "HIGH", "metric:high_cyclomatic_complexity", rel, fn.start_line, f"Método con complejidad ciclomática alta: {fn.name} ({fn.cyclomatic_complexity})."))
            if int(fn.length or 0) >= 60:
                findings.append(_metric_finding("lizard", "MEDIUM", "metric:long_method", rel, fn.start_line, f"Método muy largo: {fn.name} ({fn.length} líneas)."))
            if int(fn.parameter_count or 0) >= 6:
                findings.append(_metric_finding("lizard", "MEDIUM", "metric:too_many_parameters", rel, fn.start_line, f"Método con demasiados parámetros: {fn.name} ({fn.parameter_count})."))

        src = file_path.read_text(encoding="utf-8", errors="ignore")
        parsed = _safe_parse_java(src)
        if parsed is None:
            continue
        for _, node in parsed:
            if isinstance(node, javalang.tree.MethodDeclaration):
                fp = _method_fingerprint(node)
                method_fingerprints[fp] = method_fingerprints.get(fp, 0) + 1
                nesting = _estimate_nesting_depth(node)
                if nesting >= 4:
                    findings.append(_metric_finding("javalang", "MEDIUM", "metric:deep_nesting", rel, getattr(getattr(node, "position", None), "line", None), f"Profundidad de anidación alta ({nesting}) en método {node.name}."))

    for count in method_fingerprints.values():
        if count > 1:
            duplicated_methods += count - 1

    if duplicated_methods > 0:
        findings.append(_metric_finding("javalang", "MEDIUM", "metric:duplicated_logic", "", None, f"Se detectaron {duplicated_methods} métodos con lógica repetida."))

    return findings, {
        "total_ccn": float(total_ccn),
        "total_nloc": float(total_nloc),
        "duplicated_methods": float(duplicated_methods),
    }


def _safe_parse_java(source: str):
    try:
        return javalang.parse.parse(source)
    except Exception:
        return None


def _method_fingerprint(node) -> str:
    body = getattr(node, "body", None) or []
    compact = "".join(type(stmt).__name__ for stmt in body)
    return hashlib.sha1(f"{node.name}:{compact}".encode("utf-8")).hexdigest()


def _estimate_nesting_depth(method_node) -> int:
    max_depth = 0

    def walk(node, depth: int) -> None:
        nonlocal max_depth
        if node is None:
            return
        branch_types = (
            javalang.tree.IfStatement,
            javalang.tree.ForStatement,
            javalang.tree.WhileStatement,
            javalang.tree.DoStatement,
            javalang.tree.SwitchStatement,
            javalang.tree.TryStatement,
        )
        if isinstance(node, branch_types):
            depth += 1
            max_depth = max(max_depth, depth)
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item, depth)
            return
        for attr in getattr(node, "attrs", []) or []:
            walk(getattr(node, attr, None), depth)

    walk(getattr(method_node, "body", None) or [], 0)
    return max_depth


def _metric_finding(tool: str, severity: str, rule: str, file_path: str, line: int | None, message: str) -> NormalizedFinding:
    key = _stable_issue_key(tool, rule, file_path, line, message)
    return NormalizedFinding(
        tool=tool,
        severity=severity,
        rule=rule,
        issue_key=key,
        issue_status="OPEN",
        file_path=file_path,
        line=line,
        message=message,
        finding_type="CODE_SMELL",
        effort_minutes=None,
    )


def _build_metrics(findings: list[NormalizedFinding], lizard_summary: dict[str, float]) -> LocalAnalysisMetrics:
    bugs = sum(1 for f in findings if f.tool == "spotbugs" or f.finding_type == "BUG")
    vulnerabilities = sum(1 for f in findings if f.finding_type == "VULNERABILITY")
    code_smells = sum(1 for f in findings if f.finding_type not in {"BUG", "VULNERABILITY"})
    complexity = int(lizard_summary.get("total_ccn", 0))
    ncloc = int(lizard_summary.get("total_nloc", 0))
    duplicated_lines = int(lizard_summary.get("duplicated_methods", 0)) * 8
    duplicated_lines_density = round((duplicated_lines / ncloc) * 100, 2) if ncloc > 0 else 0.0
    maintainability_rating = 1 if code_smells < 10 else 2 if code_smells < 30 else 3 if code_smells < 60 else 4
    reliability_rating = 1 if bugs == 0 else 2 if bugs < 3 else 3
    security_rating = 1 if vulnerabilities == 0 else 2 if vulnerabilities < 3 else 3

    if vulnerabilities > 0 or bugs > 0:
        quality_gate_status = "FAILED"
    elif code_smells > 20 or complexity > 300:
        quality_gate_status = "WARN"
    else:
        quality_gate_status = "OK"

    return LocalAnalysisMetrics(
        quality_gate_status=quality_gate_status,
        bugs=bugs,
        vulnerabilities=vulnerabilities,
        code_smells=code_smells,
        complexity=complexity,
        duplicated_lines_density=duplicated_lines_density,
        duplicated_lines=duplicated_lines,
        coverage=0.0,
        lines_to_cover=0,
        ncloc=ncloc,
        reliability_rating=reliability_rating,
        security_rating=security_rating,
        maintainability_rating=maintainability_rating,
    )


def _map_pmd_priority_to_severity(priority) -> str:
    try:
        p = int(priority)
    except Exception:
        p = 3
    if p <= 1:
        return "CRITICAL"
    if p == 2:
        return "HIGH"
    if p == 3:
        return "MEDIUM"
    return "LOW"


def _map_spotbugs_priority_to_severity(priority: int) -> str:
    if priority <= 1:
        return "CRITICAL"
    if priority == 2:
        return "HIGH"
    if priority == 3:
        return "MEDIUM"
    return "LOW"


def _map_semgrep_severity(raw: str) -> str:
    val = raw.upper()
    if val in {"ERROR", "CRITICAL"}:
        return "CRITICAL"
    if val in {"WARNING", "HIGH"}:
        return "HIGH"
    if val in {"MEDIUM"}:
        return "MEDIUM"
    return "LOW"


def _stable_issue_key(tool: str, rule: str, file_path: str, line, message: str) -> str:
    payload = f"{tool}|{rule}|{file_path}|{line or 0}|{message[:200]}"
    digest = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:20]
    return f"{tool}:{digest}"


def _dedupe_findings(findings: list[NormalizedFinding]) -> list[NormalizedFinding]:
    out: list[NormalizedFinding] = []
    seen: set[tuple[str, str]] = set()
    for finding in findings:
        key = (finding.tool, finding.issue_key or _stable_issue_key(finding.tool, finding.rule, finding.file_path, finding.line, finding.message))
        if key in seen:
            continue
        seen.add(key)
        out.append(finding)
    return out
