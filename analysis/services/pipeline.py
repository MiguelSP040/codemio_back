import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import stat
from threading import BoundedSemaphore
from tempfile import TemporaryDirectory
import zipfile
from django.conf import settings
from analysis.models import AnalysisFinding, AnalysisInputType, AnalysisRun, AnalysisRunStatus
from analysis.services.sonar_runtime_service import run_sonar_analysis


_EXECUTOR = ThreadPoolExecutor(max_workers=int(getattr(settings, 'ANALYSIS_WORKERS', 2)))
_MAX_INFLIGHT_TASKS = max(int(getattr(settings, 'ANALYSIS_MAX_INFLIGHT_TASKS', 50)), 1)
_INFLIGHT_SEMAPHORE = BoundedSemaphore(value=_MAX_INFLIGHT_TASKS)


def start_analysis_run(
    *,
    run_id: int,
    source_name: str,
    source_bytes: bytes,
    input_type: str,
) -> None:
    if not _INFLIGHT_SEMAPHORE.acquire(blocking=False):
        run = AnalysisRun.objects.get(pk=run_id)
        run.status = AnalysisRunStatus.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.error_summary = 'Cola de análisis saturada. Intenta nuevamente en unos minutos.'
        run.error_detail = 'analysis_queue_overloaded'
        run.save(update_fields=['status', 'finished_at', 'error_summary', 'error_detail'])
        return
    try:
        _EXECUTOR.submit(
            _execute_analysis_run_guarded,
            run_id,
            source_name,
            source_bytes,
            input_type,
        )
    except Exception:
        _INFLIGHT_SEMAPHORE.release()
        raise


def _execute_analysis_run_guarded(
    run_id: int,
    source_name: str,
    source_bytes: bytes,
    input_type: str,
) -> None:
    try:
        _execute_analysis_run(run_id, source_name, source_bytes, input_type)
    finally:
        _INFLIGHT_SEMAPHORE.release()


def _execute_analysis_run(
    run_id: int,
    source_name: str,
    source_bytes: bytes,
    input_type: str,
) -> None:
    run = AnalysisRun.objects.get(pk=run_id)
    run.status = AnalysisRunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    run.error_summary = ''
    run.error_detail = ''
    run.save(update_fields=['status', 'started_at', 'error_summary', 'error_detail', 'updated_at'] if hasattr(run, 'updated_at') else ['status', 'started_at', 'error_summary', 'error_detail'])

    try:
        with TemporaryDirectory(prefix=f'codemio-analysis-{run_id}-') as temp_dir:
            workspace_dir = Path(temp_dir)
            source_dir = workspace_dir / 'source'
            source_dir.mkdir(parents=True, exist_ok=True)

            uploaded_file = workspace_dir / Path(source_name).name
            uploaded_file.write_bytes(source_bytes)

            if input_type == AnalysisInputType.ZIP:
                total_files = _extract_zip(uploaded_file, source_dir)
            else:
                target = source_dir / Path(source_name).name
                target.write_bytes(source_bytes)
                total_files = 1

            project_prefix = str(getattr(settings, 'SONAR_RUNTIME_PROJECT_PREFIX', 'codemio-runtime')).strip()
            sonar_project_key = f'{project_prefix}-{run.id}'
            sonar_result = run_sonar_analysis(
                source_dir=source_dir,
                workspace_dir=workspace_dir,
                project_key=sonar_project_key,
                source_name=source_name,
            )
            findings = sonar_result.findings

            AnalysisFinding.objects.filter(run=run).delete()
            AnalysisFinding.objects.bulk_create(
                [
                    AnalysisFinding(
                        run=run,
                        tool=finding.tool,
                        severity=finding.severity,
                        rule=finding.rule,
                        issue_key=finding.issue_key,
                        issue_status=finding.issue_status,
                        file_path=_normalize_file_path(finding.file_path),
                        line=finding.line,
                        message=finding.message,
                        message_es=finding.message,
                        finding_type=finding.finding_type,
                        effort_minutes=finding.effort_minutes,
                    )
                    for finding in findings
                ]
            )

            run.status = AnalysisRunStatus.DONE
            run.sonar_project_key = sonar_project_key
            run.quality_gate_status = sonar_result.metrics.quality_gate_status
            run.bugs = sonar_result.metrics.bugs
            run.vulnerabilities = sonar_result.metrics.vulnerabilities
            run.code_smells = sonar_result.metrics.code_smells
            run.complexity = sonar_result.metrics.complexity
            run.duplicated_lines_density = sonar_result.metrics.duplicated_lines_density
            run.duplicated_lines = sonar_result.metrics.duplicated_lines
            run.coverage = sonar_result.metrics.coverage
            run.lines_to_cover = sonar_result.metrics.lines_to_cover
            run.ncloc = sonar_result.metrics.ncloc
            run.reliability_rating = sonar_result.metrics.reliability_rating
            run.security_rating = sonar_result.metrics.security_rating
            run.maintainability_rating = sonar_result.metrics.maintainability_rating
            run.total_files_analyzed = total_files
            run.findings_count = len(findings)
            run.finished_at = datetime.now(timezone.utc)
            run.save(
                update_fields=[
                    'status',
                    'sonar_project_key',
                    'quality_gate_status',
                    'bugs',
                    'vulnerabilities',
                    'code_smells',
                    'complexity',
                    'duplicated_lines_density',
                    'duplicated_lines',
                    'coverage',
                    'lines_to_cover',
                    'ncloc',
                    'reliability_rating',
                    'security_rating',
                    'maintainability_rating',
                    'total_files_analyzed',
                    'findings_count',
                    'finished_at',
                ]
            )
    except Exception as exc:
        run.status = AnalysisRunStatus.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.error_summary = str(exc)[:255]
        run.error_detail = traceback.format_exc(limit=10)
        run.save(update_fields=['status', 'finished_at', 'error_summary', 'error_detail'])


def _extract_zip(zip_path: Path, target_dir: Path) -> int:
    max_files = settings.ANALYSIS_MAX_EXTRACTED_FILES
    max_bytes = settings.ANALYSIS_MAX_EXTRACTED_BYTES
    max_entries = int(getattr(settings, 'ANALYSIS_MAX_ZIP_ENTRIES', 2000))
    max_depth = int(getattr(settings, 'ANALYSIS_MAX_ZIP_PATH_DEPTH', 12))
    max_compression_ratio = float(getattr(settings, 'ANALYSIS_MAX_ZIP_COMPRESSION_RATIO', 100.0))
    max_entry_bytes = int(getattr(settings, 'ANALYSIS_MAX_ZIP_ENTRY_BYTES', max_bytes))

    extracted_count = 0
    extracted_size = 0
    processed_entries = 0
    with zipfile.ZipFile(zip_path, 'r') as archive:
        for member in archive.infolist():
            processed_entries += 1
            if processed_entries > max_entries:
                raise RuntimeError('ZIP inválido: excede el número máximo de entradas permitidas.')
            if member.is_dir():
                continue
            if _is_unsafe_zip_member(member):
                raise RuntimeError('ZIP inválido: contiene entradas no permitidas (enlace/sistema).')
            member_path = _normalize_zip_member_path(member.filename)
            clean_parts = [part for part in member_path.parts if part and part != '.']
            if _has_unsafe_path_parts(clean_parts):
                raise RuntimeError('ZIP inválido: ruta insegura detectada.')
            if len(clean_parts) > max_depth:
                raise RuntimeError('ZIP inválido: la profundidad de rutas excede el máximo permitido.')
            if member_path.suffix.lower() == '.zip':
                raise RuntimeError('ZIP inválido: no se permiten archivos ZIP anidados.')
            if member_path.suffix.lower() != '.java':
                continue
            if member.file_size > max_entry_bytes:
                raise RuntimeError('ZIP inválido: un archivo excede el tamaño máximo permitido.')
            compression_ratio = _compression_ratio(member)
            if compression_ratio > max_compression_ratio:
                raise RuntimeError('ZIP inválido: relación de compresión sospechosa detectada.')
            extracted_count += 1
            if extracted_count > max_files:
                raise RuntimeError('ZIP excede el número máximo de archivos permitidos.')
            extracted_size += int(member.file_size)
            if extracted_size > max_bytes:
                raise RuntimeError('ZIP excede el tamaño máximo permitido para extracción.')
            content = archive.read(member)
            if len(content) != int(member.file_size):
                raise RuntimeError('ZIP inválido: tamaño real de archivo no coincide con metadatos.')

            destination = _safe_destination_path(target_dir, clean_parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    if extracted_count == 0:
        raise RuntimeError('No se encontraron archivos .java en el ZIP.')
    return extracted_count


def _is_unsafe_zip_member(member: zipfile.ZipInfo) -> bool:
    mode = (member.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode) or stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode)


def _compression_ratio(member: zipfile.ZipInfo) -> float:
    file_size = int(member.file_size or 0)
    compressed_size = int(member.compress_size or 0)
    if file_size <= 0:
        return 1.0
    if compressed_size <= 0:
        return float('inf')
    return file_size / compressed_size


def _normalize_zip_member_path(raw_name: str) -> PurePosixPath:
    # Normaliza separadores Windows y limpia espacios para evitar bypasses.
    normalized_name = str(raw_name or '').replace('\\', '/').strip()
    return PurePosixPath(normalized_name)


def _has_unsafe_path_parts(parts: list[str]) -> bool:
    if not parts:
        return True
    for part in parts:
        if part in ('', '.', '..'):
            return True
        if ':' in part:
            return True
    return False


def _safe_destination_path(target_dir: Path, clean_parts: list[str]) -> Path:
    destination = target_dir.joinpath(*clean_parts)
    resolved_target = target_dir.resolve()
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(resolved_target)
    except ValueError:
        raise RuntimeError('ZIP inválido: ruta insegura detectada.')
    return destination


def _normalize_file_path(raw_path: str) -> str:
    normalized = (raw_path or '').replace('\\', '/')
    marker = '/source/'
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return Path(normalized).name if normalized else ''
