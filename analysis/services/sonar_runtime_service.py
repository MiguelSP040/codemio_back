from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.conf import settings
from analysis.services.types import NormalizedFinding, SonarAnalysisResult, SonarMetrics

_SEVERITY_MAP = {
    'BLOCKER': 'CRITICAL',
    'CRITICAL': 'HIGH',
    'MAJOR': 'MEDIUM',
    'MINOR': 'LOW',
    'INFO': 'LOW',
}


def _int_setting(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def _float_setting(name: str, default: float) -> float:
    return float(getattr(settings, name, default))


@dataclass(frozen=True)
class _SonarConfig:
    host_url: str
    token: str
    organization: str
    scanner_command: str
    qualitygate_timeout_seconds: int
    api_timeout_seconds: int


def _build_config() -> _SonarConfig:
    host_url = str(getattr(settings, 'SONAR_HOST_URL', '') or '').strip().rstrip('/')
    token = str(getattr(settings, 'SONAR_TOKEN', '') or '').strip()
    organization = str(
        getattr(settings, 'SONAR_ORGANIZATION', '') or getattr(settings, 'SONAR_ORG', '') or ''
    ).strip()
    scanner_command = str(getattr(settings, 'SONAR_SCANNER_COMMAND', 'sonar-scanner') or '').strip()
    qualitygate_timeout_seconds = int(getattr(settings, 'SONAR_QUALITYGATE_TIMEOUT_SECONDS', 180))
    api_timeout_seconds = int(getattr(settings, 'SONAR_API_TIMEOUT_SECONDS', 30))
    if not host_url or not token or not organization:
        raise RuntimeError('SonarCloud no está configurado. Define SONAR_HOST_URL, SONAR_TOKEN y SONAR_ORGANIZATION.')
    return _SonarConfig(
        host_url=host_url,
        token=token,
        organization=organization,
        scanner_command=scanner_command,
        qualitygate_timeout_seconds=qualitygate_timeout_seconds,
        api_timeout_seconds=api_timeout_seconds,
    )


def _auth_header(token: str) -> str:
    encoded = base64.b64encode(f'{token}:'.encode('utf-8')).decode('ascii')
    return f'Basic {encoded}'


def _get_json(url: str, token: str, timeout_seconds: int) -> dict:
    req = Request(
        url=url,
        headers={
            'Authorization': _auth_header(token),
            'Accept': 'application/json',
        },
        method='GET',
    )
    try:
        with urlopen(req, timeout=timeout_seconds) as response:
            payload = response.read().decode('utf-8')
    except HTTPError as exc:
        try:
            body = exc.read().decode('utf-8', errors='ignore').strip()
        except Exception:
            body = ''
        safe_body = _sanitize_secret_text(body, token)
        if body:
            raise RuntimeError(f'SonarCloud API respondió {exc.code}: {safe_body}') from exc
        raise RuntimeError(f'SonarCloud API respondió {exc.code}.') from exc
    except URLError as exc:
        raise RuntimeError('No se pudo conectar con SonarCloud API.') from exc
    try:
        return json.loads(payload or '{}')
    except json.JSONDecodeError as exc:
        raise RuntimeError('SonarCloud devolvió una respuesta JSON inválida.') from exc


def _sanitize_secret_text(text: str, token: str) -> str:
    if not text:
        return text
    safe = text
    token = (token or '').strip()
    if token:
        safe = safe.replace(token, '***')
    safe = re.sub(r'(?i)(token|authorization)\s*[:=]\s*([^\s,;]+)', r'\1=***', safe)
    return safe


def _run_scanner(
    workspace_dir: Path,
    project_key: str,
    source_name: str,
    config: _SonarConfig,
) -> None:
    properties_file = workspace_dir / 'sonar-project.properties'
    properties_file.write_text(
        '\n'.join(
            [
                f'sonar.host.url={config.host_url}',
                f'sonar.organization={config.organization}',
                f'sonar.projectKey={project_key}',
                f'sonar.projectName={source_name}',
                'sonar.projectVersion=runtime',
                'sonar.sources=source',
                'sonar.inclusions=**/*.java',
                'sonar.exclusions=**/*.zip',
                'sonar.sourceEncoding=UTF-8',
                'sonar.language=java',
                'sonar.qualitygate.wait=false',
                'sonar.scanner.skipJreProvisioning=true',
            ]
        ),
        encoding='utf-8',
    )
    command = [
        config.scanner_command,
        f'-Dproject.settings={properties_file}',
    ]
    env = {**os.environ, 'SONAR_TOKEN': config.token}
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace_dir),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=int(getattr(settings, 'ANALYSIS_TOOL_TIMEOUT_SECONDS', 120)),
        )
    except FileNotFoundError as exc:
        raise RuntimeError('No se encontró el comando sonar-scanner.') from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('sonar-scanner excedió el tiempo máximo de ejecución.') from exc
    if result.returncode != 0:
        stderr = (result.stderr or '').strip()
        stdout = (result.stdout or '').strip()
        combined_output = '\n'.join([part for part in [stderr, stdout] if part]).strip()
        quality_gate_status = _extract_quality_gate_status(combined_output)
        # If scanner reached a quality gate result, treat it as a completed analysis outcome.
        if quality_gate_status in {'FAILED', 'ERROR'}:
            return
        raise RuntimeError(f'SonarScanner falló: {combined_output or "sin detalle"}')


def _extract_quality_gate_status(scanner_output: str) -> str:
    marker = 'QUALITY GATE STATUS:'
    for raw_line in scanner_output.splitlines():
        line = raw_line.strip()
        if marker not in line:
            continue
        status_part = line.split(marker, 1)[1].strip()
        if not status_part:
            continue
        status_token = status_part.split()[0].strip().upper()
        if status_token:
            return status_token
    return ''


def _extract_effort_minutes(effort: str | None) -> int | None:
    if not effort:
        return None
    # Sonar usa formato tipo "5min", "1h 10min", etc.
    tokens = effort.replace('h', 'h ').replace('min', 'min ').split()
    minutes = 0
    try:
        idx = 0
        while idx < len(tokens):
            value = int(tokens[idx])
            unit = tokens[idx + 1] if idx + 1 < len(tokens) else ''
            if unit.startswith('h'):
                minutes += value * 60
            else:
                minutes += value
            idx += 2
    except Exception:
        return None
    return minutes


def _fetch_issues(project_key: str, config: _SonarConfig) -> list[NormalizedFinding]:
    def _build_query(page: int, page_size: int) -> str:
        return urlencode(
            {
                'componentKeys': project_key,
                'organization': config.organization,
                'types': 'BUG,VULNERABILITY,CODE_SMELL',
                'statuses': 'OPEN,CONFIRMED,REOPENED,RESOLVED,CLOSED',
                'ps': page_size,
                'p': page,
            }
        )

    def _to_finding(issue: dict) -> NormalizedFinding:
        text_range = issue.get('textRange') or {}
        return NormalizedFinding(
            tool='sonarcloud',
            severity=_SEVERITY_MAP.get(str(issue.get('severity', '')).upper(), 'LOW'),
            rule=str(issue.get('rule') or ''),
            issue_key=str(issue.get('key') or ''),
            issue_status=str(issue.get('status') or ''),
            file_path=_normalize_component_path(str(issue.get('component') or '')),
            line=int(text_range.get('startLine')) if text_range.get('startLine') else None,
            message=str(issue.get('message') or ''),
            finding_type=str(issue.get('type') or ''),
            effort_minutes=_extract_effort_minutes(issue.get('effort')),
        )

    findings: list[NormalizedFinding] = []
    page = 1
    page_size = 500
    while True:
        query = _build_query(page=page, page_size=page_size)
        payload = _get_json(
            f'{config.host_url}/api/issues/search?{query}',
            token=config.token,
            timeout_seconds=config.api_timeout_seconds,
        )
        issues = payload.get('issues') or []
        for issue in issues:
            findings.append(_to_finding(issue))
        paging = payload.get('paging') or {}
        total = int(paging.get('total') or 0)
        if page * page_size >= total:
            break
        page += 1
    return findings


def _metric_value(measures: dict[str, str], key: str, default: str = '0') -> str:
    return str(measures.get(key, default) or default)


def _normalize_component_path(raw_component: str) -> str:
    if not raw_component:
        return ''
    # SonarCloud component suele venir como "<project_key>:<relative/path>".
    if ':' in raw_component:
        return raw_component.split(':', 1)[1]
    return raw_component


def _fetch_metrics(project_key: str, config: _SonarConfig) -> SonarMetrics:
    metric_keys = (
        'bugs,vulnerabilities,code_smells,complexity,duplicated_lines_density,duplicated_lines,'
        'coverage,lines_to_cover,ncloc,alert_status,reliability_rating,security_rating,sqale_rating'
    )
    query = urlencode(
        {
            'component': project_key,
            'organization': config.organization,
            'metricKeys': metric_keys,
        }
    )
    payload = _get_json(
        f'{config.host_url}/api/measures/component?{query}',
        token=config.token,
        timeout_seconds=config.api_timeout_seconds,
    )
    measures_raw = (payload.get('component') or {}).get('measures') or []
    measures = {item.get('metric'): item.get('value') for item in measures_raw if item.get('metric')}
    bugs = int(float(_metric_value(measures, 'bugs')))
    vulnerabilities = int(float(_metric_value(measures, 'vulnerabilities')))
    code_smells = int(float(_metric_value(measures, 'code_smells')))
    complexity = int(float(_metric_value(measures, 'complexity')))
    duplicated_lines_density = float(_metric_value(measures, 'duplicated_lines_density'))
    duplicated_lines = int(float(_metric_value(measures, 'duplicated_lines')))
    coverage = float(_metric_value(measures, 'coverage'))
    lines_to_cover = int(float(_metric_value(measures, 'lines_to_cover')))
    ncloc = int(float(_metric_value(measures, 'ncloc')))
    reliability_rating = int(float(_metric_value(measures, 'reliability_rating')))
    security_rating = int(float(_metric_value(measures, 'security_rating')))
    maintainability_rating = int(float(_metric_value(measures, 'sqale_rating')))
    raw_quality_gate_status = str(_metric_value(measures, 'alert_status', 'NONE')).upper()
    quality_gate_status = _evaluate_mvp_quality_gate(
        raw_quality_gate_status=raw_quality_gate_status,
        bugs=bugs,
        vulnerabilities=vulnerabilities,
        code_smells=code_smells,
        reliability_rating=reliability_rating,
        security_rating=security_rating,
        maintainability_rating=maintainability_rating,
        coverage=coverage,
        lines_to_cover=lines_to_cover,
    )
    return SonarMetrics(
        quality_gate_status=quality_gate_status,
        bugs=bugs,
        vulnerabilities=vulnerabilities,
        code_smells=code_smells,
        complexity=complexity,
        duplicated_lines_density=duplicated_lines_density,
        duplicated_lines=duplicated_lines,
        coverage=coverage,
        lines_to_cover=lines_to_cover,
        ncloc=ncloc,
        reliability_rating=reliability_rating,
        security_rating=security_rating,
        maintainability_rating=maintainability_rating,
    )


def _evaluate_mvp_quality_gate(
    *,
    raw_quality_gate_status: str,
    bugs: int,
    vulnerabilities: int,
    code_smells: int,
    reliability_rating: int,
    security_rating: int,
    maintainability_rating: int,
    coverage: float,
    lines_to_cover: int,
) -> str:
    """
    MVP policy:
    - Strict on security/reliability.
    - Flexible on maintainability and style, surfaced as WARN.
    """
    max_security_rating = _int_setting('ANALYSIS_GATE_MAX_SECURITY_RATING', 1)
    max_reliability_rating = _int_setting('ANALYSIS_GATE_MAX_RELIABILITY_RATING', 1)
    max_maintainability_rating = _int_setting('ANALYSIS_GATE_MAX_MAINTAINABILITY_RATING', 2)
    warn_code_smells_threshold = _int_setting('ANALYSIS_GATE_WARN_CODE_SMELLS_THRESHOLD', 20)
    warn_min_coverage = _float_setting('ANALYSIS_GATE_WARN_MIN_COVERAGE', 60.0)

    hard_fail = (
        vulnerabilities > 0
        or bugs > 0
        or security_rating > max_security_rating
        or reliability_rating > max_reliability_rating
    )
    if hard_fail:
        return 'FAILED'

    warning = (
        maintainability_rating > max_maintainability_rating
        or code_smells > warn_code_smells_threshold
        or (lines_to_cover > 0 and coverage < warn_min_coverage)
        or raw_quality_gate_status in {'WARN', 'WARNING'}
    )
    if warning:
        return 'WARN'

    return 'OK'


def push_sonar_scan_only(
    *,
    workspace_dir: Path,
    project_key: str,
    source_name: str,
) -> None:

    config = _build_config()
    _run_scanner(
        workspace_dir=workspace_dir,
        project_key=project_key,
        source_name=source_name,
        config=config,
    )


def run_sonar_analysis(
    *,
    workspace_dir: Path,
    project_key: str,
    source_name: str,
) -> SonarAnalysisResult:

    config = _build_config()
    push_sonar_scan_only(
        workspace_dir=workspace_dir,
        project_key=project_key,
        source_name=source_name,
    )
    findings = _fetch_issues(project_key=project_key, config=config)
    metrics = _fetch_metrics(project_key=project_key, config=config)
    return SonarAnalysisResult(findings=findings, metrics=metrics)


def fetch_sonar_issues_public(project_key: str) -> list[NormalizedFinding]:
    config = _build_config()
    return _fetch_issues(project_key=project_key, config=config)


def fetch_sonar_metrics_public(project_key: str) -> SonarMetrics:
    config = _build_config()
    return _fetch_metrics(project_key=project_key, config=config)
