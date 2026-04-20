import logging
import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import stat
from threading import BoundedSemaphore
from tempfile import TemporaryDirectory
import time
import zipfile
from django.conf import settings
from analysis.instrumentation import analysis_instr_log
from analysis.models import AnalysisFileMetric, AnalysisInputType, AnalysisRun, AnalysisRunStatus
from analysis.services.java_syntax_metrics import extract_java_syntax_metrics
from analysis.services.sonar_runtime_service import SonarScannerError, push_sonar_scan_only

logger = logging.getLogger(__name__)

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
        analysis_instr_log(
            logger,
            'analysis_run_failed_before_webhook',
            run_id=run.id,
            project_id=run.project_id,
            status=run.status,
            sonar_project_key=(run.sonar_project_key or '')[:80],
            input_type=run.input_type,
            original_filename=(run.original_filename or '')[:120],
            duration_ms=0,
            error_type='queue_saturated',
            error_message='analysis_queue_overloaded',
        )
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


def _prepare_workspace(source_name: str, source_bytes: bytes, input_type: str, run_id: int) -> tuple[Path, Path, int, str, object]:
    temp_dir_ctx = TemporaryDirectory(prefix=f'codemio-analysis-{run_id}-')
    workspace_dir = Path(temp_dir_ctx.name)
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
    sonar_project_key = f'{project_prefix}-{run_id}'
    return workspace_dir, source_dir, total_files, sonar_project_key, temp_dir_ctx


def _save_waiting_run_state(run: AnalysisRun, *, sonar_project_key: str, syntax_metrics, total_files: int) -> None:
    previous_status = run.status
    run.status = AnalysisRunStatus.WAITING_SONAR_WEBHOOK
    run.sonar_project_key = sonar_project_key
    run.classes_count = syntax_metrics.classes_count
    run.methods_count = syntax_metrics.methods_count
    run.parameters_count = syntax_metrics.parameters_count
    run.inheritance_count = syntax_metrics.inheritance_count
    run.interclass_calls_count = syntax_metrics.interclass_calls_count
    run.total_files_analyzed = total_files
    run.findings_count = 0
    run.quality_gate_status = ''
    run.bugs = 0
    run.vulnerabilities = 0
    run.code_smells = 0
    run.complexity = 0
    run.duplicated_lines_density = 0.0
    run.duplicated_lines = 0
    run.coverage = 0.0
    run.lines_to_cover = 0
    run.ncloc = 0
    run.reliability_rating = 0
    run.security_rating = 0
    run.maintainability_rating = 0
    run.error_summary = ''
    run.error_detail = ''
    run.save(
        update_fields=[
            'status',
            'sonar_project_key',
            'classes_count',
            'methods_count',
            'parameters_count',
            'inheritance_count',
            'interclass_calls_count',
            'total_files_analyzed',
            'findings_count',
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
            'error_summary',
            'error_detail',
        ]
    )
    logger.info(
        'event=analysis_run_status_transition run_id=%s from_status=%s to_status=%s reason=%s',
        run.id,
        previous_status,
        run.status,
        'scanner_completed',
    )


def _process_analysis_attempt(run: AnalysisRun, *, run_id: int, source_name: str, source_bytes: bytes, input_type: str) -> tuple[int, str]:
    workspace_dir, source_dir, total_files, sonar_project_key, temp_ctx = _prepare_workspace(
        source_name=source_name,
        source_bytes=source_bytes,
        input_type=input_type,
        run_id=run_id,
    )
    try:
        try:
            push_sonar_scan_only(
                workspace_dir=workspace_dir,
                project_key=sonar_project_key,
                source_name=source_name,
                run_id=run_id,
                input_type=input_type,
                source_size_bytes=len(source_bytes),
                total_files=total_files,
            )
        except SonarScannerError as exc:
            logger.exception(
                'event=sonar_scanner_exception run_id=%s sonar_project_key=%s exception_type=%s exception_message=%s command_preview=%s stdout_preview=%s stderr_preview=%s',
                run_id,
                sonar_project_key,
                type(exc).__name__,
                str(exc),
                exc.command_preview,
                exc.stdout_preview,
                exc.stderr_preview,
            )
            raise
        except Exception as exc:
            logger.exception(
                'event=sonar_scanner_exception run_id=%s sonar_project_key=%s exception_type=%s exception_message=%s command_preview=%s',
                run_id,
                sonar_project_key,
                type(exc).__name__,
                str(exc),
                '',
            )
            raise
        syntax_metrics = extract_java_syntax_metrics(source_dir)
    finally:
        temp_ctx.cleanup()

    AnalysisFileMetric.objects.filter(run=run).delete()
    AnalysisFileMetric.objects.bulk_create(
        [
            AnalysisFileMetric(
                run=run,
                file_path=item.file_path,
                classes_count=item.classes_count,
                methods_count=item.methods_count,
                parameters_count=item.parameters_count,
                inheritance_count=item.inheritance_count,
                interclass_calls_count=item.interclass_calls_count,
            )
            for item in syntax_metrics.files
        ]
    )
    _save_waiting_run_state(
        run,
        sonar_project_key=sonar_project_key,
        syntax_metrics=syntax_metrics,
        total_files=total_files,
    )
    return total_files, sonar_project_key


def _execute_analysis_run(
    run_id: int,
    source_name: str,
    source_bytes: bytes,
    input_type: str,
) -> None:
    run = AnalysisRun.objects.get(pk=run_id)
    _mark_run_started(run)
    t_pipeline = time.perf_counter()
    analysis_instr_log(
        logger,
        'analysis_run_started',
        run_id=run.id,
        project_id=run.project_id,
        status=run.status,
        sonar_project_key=(run.sonar_project_key or '')[:80],
        input_type=run.input_type,
        original_filename=(run.original_filename or '')[:120],
        duration_ms=0,
    )
    logger.info(
        'event=analysis_run_started run_id=%s project_id=%s input_type=%s original_filename=%s logical_filename=%s created_at=%s started_at=%s status=%s',
        run.id,
        run.project_id,
        run.input_type,
        (run.original_filename or '')[:120],
        (run.logical_filename or '')[:120],
        run.created_at.isoformat() if run.created_at else '',
        run.started_at.isoformat() if run.started_at else '',
        run.status,
    )

    max_retries = max(int(getattr(settings, 'ANALYSIS_RETRY_ATTEMPTS', 2)), 0)
    retry_backoff_seconds = max(float(getattr(settings, 'ANALYSIS_RETRY_BACKOFF_SECONDS', 1.5)), 0.0)

    for attempt in range(1, max_retries + 2):
        try:
            total_files, sonar_project_key = _process_analysis_attempt(
                run,
                run_id=run_id,
                source_name=source_name,
                source_bytes=source_bytes,
                input_type=input_type,
            )
            _log_waiting_for_webhook(
                run,
                t_pipeline=t_pipeline,
                sonar_project_key=sonar_project_key,
                input_type=input_type,
                source_name=source_name,
                total_files=total_files,
            )
            return
        except Exception as exc:
            trace = traceback.format_exc(limit=10)
            if attempt <= max_retries:
                _persist_retry_state(
                    run,
                    attempt=attempt,
                    total_attempts=max_retries + 1,
                    trace=trace,
                    retry_backoff_seconds=retry_backoff_seconds,
                )
                continue

            _persist_failed_run_state(
                run,
                exc=exc,
                trace=trace,
                t_pipeline=t_pipeline,
                input_type=input_type,
                source_name=source_name,
                attempt=attempt,
            )
            return


def _mark_run_started(run: AnalysisRun) -> None:
    previous_status = run.status
    run.status = AnalysisRunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    run.error_summary = ''
    run.error_detail = ''
    update_fields = ['status', 'started_at', 'error_summary', 'error_detail']
    if hasattr(run, 'updated_at'):
        update_fields.append('updated_at')
    run.save(update_fields=update_fields)
    logger.info(
        'event=analysis_run_status_transition run_id=%s from_status=%s to_status=%s reason=%s',
        run.id,
        previous_status,
        run.status,
        'worker_started',
    )


def _log_waiting_for_webhook(
    run: AnalysisRun,
    *,
    t_pipeline: float,
    sonar_project_key: str,
    input_type: str,
    source_name: str,
    total_files: int,
) -> None:
    duration_ms = int((time.perf_counter() - t_pipeline) * 1000)
    analysis_instr_log(
        logger,
        'analysis_run_waiting_sonar_webhook',
        run_id=run.id,
        project_id=run.project_id,
        status=run.status,
        sonar_project_key=(sonar_project_key or '')[:120],
        input_type=input_type,
        original_filename=(source_name or '')[:120],
        duration_ms=duration_ms,
        total_files_analyzed=total_files,
    )


def _persist_retry_state(
    run: AnalysisRun,
    *,
    attempt: int,
    total_attempts: int,
    trace: str,
    retry_backoff_seconds: float,
) -> None:
    run.error_summary = (f'Intento {attempt} de {total_attempts} falló. Reintentando análisis...')[:255]
    run.error_detail = trace
    run.save(update_fields=['error_summary', 'error_detail'])
    sleep_seconds = retry_backoff_seconds * attempt
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def _persist_failed_run_state(
    run: AnalysisRun,
    *,
    exc: Exception,
    trace: str,
    t_pipeline: float,
    input_type: str,
    source_name: str,
    attempt: int,
) -> None:
    previous_status = run.status
    category = 'unknown'
    scanner_stdout_preview = ''
    scanner_stderr_preview = ''
    command_preview = ''
    if isinstance(exc, SonarScannerError):
        category = exc.category
        scanner_stdout_preview = exc.stdout_preview
        scanner_stderr_preview = exc.stderr_preview
        command_preview = exc.command_preview
    run.status = AnalysisRunStatus.FAILED
    run.finished_at = datetime.now(timezone.utc)
    run.error_summary = f'[{category}] {str(exc)}'[:255]
    run.error_detail = trace
    run.save(update_fields=['status', 'finished_at', 'error_summary', 'error_detail'])
    logger.info(
        'event=analysis_run_status_transition run_id=%s from_status=%s to_status=%s reason=%s error_summary=%s',
        run.id,
        previous_status,
        run.status,
        'pipeline_exception',
        run.error_summary,
    )
    logger.error(
        'event=analysis_run_failed_scanner run_id=%s sonar_project_key=%s category=%s error_summary=%s error_detail=%s command_preview=%s stdout_preview=%s stderr_preview=%s',
        run.id,
        (run.sonar_project_key or '')[:120],
        category,
        run.error_summary,
        (trace or '')[:1200],
        command_preview,
        scanner_stdout_preview,
        scanner_stderr_preview,
    )
    duration_ms = int((time.perf_counter() - t_pipeline) * 1000)
    analysis_instr_log(
        logger,
        'analysis_run_failed_before_webhook',
        run_id=run.id,
        project_id=run.project_id,
        status=run.status,
        sonar_project_key=(run.sonar_project_key or '')[:120],
        input_type=input_type,
        original_filename=(source_name or '')[:120],
        duration_ms=duration_ms,
        error_type=type(exc).__name__,
        error_message=str(exc)[:200],
        attempt=attempt,
    )


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
            clean_parts = _validate_zip_member(
                member,
                max_depth=max_depth,
                max_entry_bytes=max_entry_bytes,
                max_compression_ratio=max_compression_ratio,
            )
            if clean_parts is None:
                continue
            extracted_count, extracted_size = _check_extraction_limits(
                extracted_count=extracted_count,
                extracted_size=extracted_size,
                file_size=int(member.file_size),
                max_files=max_files,
                max_bytes=max_bytes,
            )
            content = archive.read(member)
            if len(content) != int(member.file_size):
                raise RuntimeError('ZIP inválido: tamaño real de archivo no coincide con metadatos.')

            destination = _safe_destination_path(target_dir, clean_parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    if extracted_count == 0:
        raise RuntimeError('No se encontraron archivos .java en el ZIP.')
    return extracted_count


def _validate_zip_member(
    member: zipfile.ZipInfo,
    *,
    max_depth: int,
    max_entry_bytes: int,
    max_compression_ratio: float,
) -> list[str] | None:
    if member.is_dir():
        return None
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
        return None
    if member.file_size > max_entry_bytes:
        raise RuntimeError('ZIP inválido: un archivo excede el tamaño máximo permitido.')
    compression_ratio = _compression_ratio(member)
    if compression_ratio > max_compression_ratio:
        raise RuntimeError('ZIP inválido: relación de compresión sospechosa detectada.')
    return clean_parts


def _check_extraction_limits(
    *,
    extracted_count: int,
    extracted_size: int,
    file_size: int,
    max_files: int,
    max_bytes: int,
) -> tuple[int, int]:
    new_count = extracted_count + 1
    if new_count > max_files:
        raise RuntimeError('ZIP excede el número máximo de archivos permitidos.')
    new_size = extracted_size + file_size
    if new_size > max_bytes:
        raise RuntimeError('ZIP excede el tamaño máximo permitido para extracción.')
    return new_count, new_size


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
