from __future__ import annotations

import base64
import json
import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from django.conf import settings
from analysis.instrumentation import analysis_instr_log
from analysis.services.types import NormalizedFinding, SonarAnalysisResult, SonarMetrics

logger = logging.getLogger(__name__)

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


class SonarScannerError(RuntimeError):
    def __init__(
        self,
        *,
        category: str,
        message: str,
        stdout_preview: str = '',
        stderr_preview: str = '',
        command_preview: str = '',
        return_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.stdout_preview = stdout_preview
        self.stderr_preview = stderr_preview
        self.command_preview = command_preview
        self.return_code = return_code


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


def _truncate_output(text: str, *, max_chars: int = 1400) -> str:
    raw = (text or '').strip()
    if len(raw) <= max_chars:
        return raw
    head = raw[: max_chars // 2]
    tail = raw[-max_chars // 2 :]
    return f'{head}\n...<truncated>...\n{tail}'


def _command_preview(command: list[str], token: str) -> str:
    raw = ' '.join(str(part) for part in command)
    return _sanitize_secret_text(raw, token)


def _classify_scanner_failure(*, stderr_text: str, stdout_text: str, exception_type: str = '') -> str:
    blob = f'{stderr_text}\n{stdout_text}'.lower()
    if exception_type == 'TimeoutExpired':
        return 'timeout'
    if 'no se encontró el comando sonar-scanner' in blob or 'not recognized' in blob or 'no such file' in blob:
        return 'scanner_not_found'
    if 'java' in blob and ('not found' in blob or 'not recognized' in blob or 'could not find java' in blob):
        return 'java_not_found'
    if '401' in blob or '403' in blob or 'not authorized' in blob or 'unauthorized' in blob:
        return 'sonar_auth_error'
    if 'unknownhost' in blob or 'connection' in blob or 'timed out' in blob or 'unable to execute' in blob:
        return 'sonar_network_error'
    if exception_type == 'RuntimeError':
        return 'scanner_exit_nonzero'
    return 'unknown'


def _write_sonar_properties_file(workspace_dir: Path, *, config: _SonarConfig, project_key: str, source_name: str) -> Path:
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
    return properties_file


def _log_scanner_prepare(
    *,
    run_id: int | None,
    project_key: str,
    config: _SonarConfig,
    timeout_seconds: int,
    java_path: str,
    workspace_dir: Path,
    input_type: str,
    source_size_bytes: int | None,
    total_files: int | None,
) -> None:
    analysis_instr_log(
        logger,
        'sonar_scanner_prepare',
        run_id=run_id or '',
        sonar_project_key=project_key,
        sonar_host_url=config.host_url,
        sonar_organization=config.organization,
        scanner_command_resolved=config.scanner_command,
        timeout_seconds=timeout_seconds,
        java_path=java_path or 'missing',
        working_dir=str(workspace_dir),
        input_type=input_type,
        source_size_bytes=source_size_bytes if source_size_bytes is not None else '',
        total_files=total_files if total_files is not None else '',
    )
    logger.info(
        'event=sonar_scanner_prepare run_id=%s sonar_project_key=%s scanner_command=%s timeout_seconds=%s java_path=%s cwd=%s input_type=%s total_files=%s source_size_bytes=%s',
        run_id,
        project_key,
        config.scanner_command,
        timeout_seconds,
        java_path or 'missing',
        str(workspace_dir),
        input_type,
        total_files if total_files is not None else '',
        source_size_bytes if source_size_bytes is not None else '',
    )


def _run_scanner_subprocess(
    *,
    command: list[str],
    workspace_dir: Path,
    env: dict[str, str],
    timeout_seconds: int,
    run_id: int | None,
    project_key: str,
    cmd_preview: str,
    token: str,
) -> tuple[subprocess.CompletedProcess[str], str, str]:
    t0 = time.perf_counter()
    logger.info(
        'event=sonar_scanner_subprocess_start run_id=%s sonar_project_key=%s cwd=%s timeout_seconds=%s command_preview=%s',
        run_id,
        project_key,
        str(workspace_dir),
        timeout_seconds,
        cmd_preview,
    )
    try:
        result = subprocess.run(
            command,
            cwd=str(workspace_dir),
            env=env,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except FileNotFoundError as exc:
        raise SonarScannerError(
            category='scanner_not_found',
            message='No se encontró el comando sonar-scanner.',
            command_preview=cmd_preview,
        ) from exc
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        stdout_preview = _truncate_output(_sanitize_secret_text((exc.stdout or ''), token))
        stderr_preview = _truncate_output(_sanitize_secret_text((exc.stderr or ''), token))
        logger.error(
            'event=sonar_scanner_timeout run_id=%s sonar_project_key=%s timeout_seconds=%s duration_ms=%s command_preview=%s stdout_preview=%s stderr_preview=%s error=%s',
            run_id,
            project_key,
            timeout_seconds,
            duration_ms,
            cmd_preview,
            stdout_preview,
            stderr_preview,
            str(exc),
        )
        raise SonarScannerError(
            category='timeout',
            message='sonar-scanner excedió el tiempo máximo de ejecución.',
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            command_preview=cmd_preview,
        ) from exc
    duration_ms = int((time.perf_counter() - t0) * 1000)
    stdout_preview = _truncate_output(_sanitize_secret_text((result.stdout or ''), token))
    stderr_preview = _truncate_output(_sanitize_secret_text((result.stderr or ''), token))
    logger.info(
        'event=sonar_scanner_subprocess_finished run_id=%s sonar_project_key=%s return_code=%s duration_ms=%s stdout_preview=%s stderr_preview=%s',
        run_id,
        project_key,
        result.returncode,
        duration_ms,
        stdout_preview,
        stderr_preview,
    )
    return result, stdout_preview, stderr_preview


def _raise_nonzero_scanner_result(
    *,
    result: subprocess.CompletedProcess[str],
    stdout_preview: str,
    stderr_preview: str,
    cmd_preview: str,
) -> None:
    stderr = (result.stderr or '').strip()
    stdout = (result.stdout or '').strip()
    combined_output = '\n'.join([part for part in [stderr, stdout] if part]).strip()
    quality_gate_status = _extract_quality_gate_status(combined_output)
    if quality_gate_status in {'FAILED', 'ERROR'}:
        return
    category = _classify_scanner_failure(stderr_text=stderr, stdout_text=stdout, exception_type='RuntimeError')
    raise SonarScannerError(
        category=category,
        message=f'SonarScanner falló: {combined_output or "sin detalle"}',
        stdout_preview=stdout_preview,
        stderr_preview=stderr_preview,
        command_preview=cmd_preview,
        return_code=result.returncode,
    )


def _run_scanner(
    workspace_dir: Path,
    project_key: str,
    source_name: str,
    config: _SonarConfig,
    *,
    run_id: int | None = None,
    input_type: str = '',
    source_size_bytes: int | None = None,
    total_files: int | None = None,
) -> None:
    properties_file = _write_sonar_properties_file(
        workspace_dir,
        config=config,
        project_key=project_key,
        source_name=source_name,
    )
    command = [
        config.scanner_command,
        f'-Dproject.settings={properties_file}',
    ]
    env = {**os.environ, 'SONAR_TOKEN': config.token}
    timeout_seconds = int(getattr(settings, 'ANALYSIS_TOOL_TIMEOUT_SECONDS', 120))
    java_path = shutil.which('java') or ''
    cmd_preview = _command_preview(command, config.token)
    _log_scanner_prepare(
        run_id=run_id,
        project_key=project_key,
        config=config,
        timeout_seconds=timeout_seconds,
        java_path=java_path,
        workspace_dir=workspace_dir,
        input_type=input_type,
        source_size_bytes=source_size_bytes,
        total_files=total_files,
    )
    result, stdout_preview, stderr_preview = _run_scanner_subprocess(
        command=command,
        workspace_dir=workspace_dir,
        env=env,
        timeout_seconds=timeout_seconds,
        run_id=run_id,
        project_key=project_key,
        cmd_preview=cmd_preview,
        token=config.token,
    )
    if result.returncode != 0:
        _raise_nonzero_scanner_result(
            result=result,
            stdout_preview=stdout_preview,
            stderr_preview=stderr_preview,
            cmd_preview=cmd_preview,
        )


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


def _issues_query(*, project_key: str, organization: str, page: int, page_size: int) -> str:
    return urlencode(
        {
            'componentKeys': project_key,
            'organization': organization,
            'types': 'BUG,VULNERABILITY,CODE_SMELL',
            'statuses': 'OPEN,CONFIRMED,REOPENED,RESOLVED,CLOSED',
            'ps': page_size,
            'p': page,
        }
    )


def _issue_to_finding(issue: dict) -> NormalizedFinding:
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


def _fetch_issues(project_key: str, config: _SonarConfig) -> list[NormalizedFinding]:

    findings: list[NormalizedFinding] = []
    page = 1
    page_size = 500
    while True:
        query = _issues_query(
            project_key=project_key,
            organization=config.organization,
            page=page,
            page_size=page_size,
        )
        payload = _get_json(
            f'{config.host_url}/api/issues/search?{query}',
            token=config.token,
            timeout_seconds=config.api_timeout_seconds,
        )
        issues = payload.get('issues') or []
        findings.extend(_issue_to_finding(issue) for issue in issues)
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
    run_id: int | None = None,
    input_type: str = '',
    source_size_bytes: int | None = None,
    total_files: int | None = None,
) -> None:

    config = _build_config()
    try:
        _run_scanner(
            workspace_dir=workspace_dir,
            project_key=project_key,
            source_name=source_name,
            config=config,
            run_id=run_id,
            input_type=input_type,
            source_size_bytes=source_size_bytes,
            total_files=total_files,
        )
    except SonarScannerError:
        raise
    except Exception as exc:
        logger.exception(
            'event=sonar_scanner_exception run_id=%s sonar_project_key=%s exception_type=%s exception_message=%s command_preview=%s',
            run_id,
            project_key,
            type(exc).__name__,
            str(exc),
            '',
        )
        raise SonarScannerError(
            category='unknown',
            message=f'Fallo inesperado al ejecutar sonar-scanner: {exc}',
            command_preview='',
        ) from exc


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
