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
from analysis.models import AnalysisFileMetric, AnalysisFinding, AnalysisInputType, AnalysisRun, AnalysisRunStatus
from analysis.services.java_content_validator import validate_java_source_bytes
from analysis.services.finding_translator import translate_finding_message
from analysis.services.local_analysis_service import run_local_analysis

_EXECUTOR = ThreadPoolExecutor(max_workers=int(getattr(settings, "ANALYSIS_WORKERS", 2)))
_MAX_INFLIGHT_TASKS = max(int(getattr(settings, "ANALYSIS_MAX_INFLIGHT_TASKS", 50)), 1)
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


def _prepare_workspace(
    source_name: str, source_bytes: bytes, input_type: str, run_id: int
) -> tuple[Path, Path, int, list[str], object]:
    temp_dir_ctx = TemporaryDirectory(prefix=f'codemio-analysis-{run_id}-')
    workspace_dir = Path(temp_dir_ctx.name)
    source_dir = workspace_dir / 'source'
    source_dir.mkdir(parents=True, exist_ok=True)
    uploaded_file = workspace_dir / Path(source_name).name
    uploaded_file.write_bytes(source_bytes)
    validation_warnings: list[str] = []
    if input_type == AnalysisInputType.ZIP:
        total_files = _extract_zip(uploaded_file, source_dir, validation_warnings=validation_warnings)
    else:
        target = source_dir / Path(source_name).name
        target.write_bytes(source_bytes)
        total_files = 1
    return workspace_dir, source_dir, total_files, validation_warnings, temp_dir_ctx


def _save_done_state(run: AnalysisRun, *, analysis_result, total_files: int) -> None:
    run.status = AnalysisRunStatus.DONE
    run.sonar_project_key = ""
    run.sonar_task_id = ""
    run.sonar_analysis_id = ""
    run.webhook_received_at = None
    run.last_sonar_sync_at = None
    run.classes_count = analysis_result.syntax_metrics.classes_count
    run.methods_count = analysis_result.syntax_metrics.methods_count
    run.parameters_count = analysis_result.syntax_metrics.parameters_count
    run.inheritance_count = analysis_result.syntax_metrics.inheritance_count
    run.interclass_calls_count = analysis_result.syntax_metrics.interclass_calls_count
    run.total_files_analyzed = total_files
    run.findings_count = len(analysis_result.findings)
    run.quality_gate_status = analysis_result.metrics.quality_gate_status
    run.bugs = analysis_result.metrics.bugs
    run.vulnerabilities = analysis_result.metrics.vulnerabilities
    run.code_smells = analysis_result.metrics.code_smells
    run.complexity = analysis_result.metrics.complexity
    run.duplicated_lines_density = analysis_result.metrics.duplicated_lines_density
    run.duplicated_lines = analysis_result.metrics.duplicated_lines
    run.coverage = analysis_result.metrics.coverage
    run.lines_to_cover = analysis_result.metrics.lines_to_cover
    run.ncloc = analysis_result.metrics.ncloc
    run.reliability_rating = analysis_result.metrics.reliability_rating
    run.security_rating = analysis_result.metrics.security_rating
    run.maintainability_rating = analysis_result.metrics.maintainability_rating
    run.error_summary = ""
    run.error_detail = ""
    run.finished_at = datetime.now(timezone.utc)
    run.save(
        update_fields=[
            "status",
            "sonar_project_key",
            "sonar_task_id",
            "sonar_analysis_id",
            "webhook_received_at",
            "last_sonar_sync_at",
            "classes_count",
            "methods_count",
            "parameters_count",
            "inheritance_count",
            "interclass_calls_count",
            "total_files_analyzed",
            "findings_count",
            "quality_gate_status",
            "bugs",
            "vulnerabilities",
            "code_smells",
            "complexity",
            "duplicated_lines_density",
            "duplicated_lines",
            "coverage",
            "lines_to_cover",
            "ncloc",
            "reliability_rating",
            "security_rating",
            "maintainability_rating",
            "error_summary",
            "error_detail",
            "finished_at",
        ]
    )


def _execute_analysis_run(
    run_id: int,
    source_name: str,
    source_bytes: bytes,
    input_type: str,
) -> None:
    run = AnalysisRun.objects.get(pk=run_id)
    _mark_run_started(run)

    max_retries = max(int(getattr(settings, "ANALYSIS_RETRY_ATTEMPTS", 2)), 0)
    retry_backoff_seconds = max(float(getattr(settings, "ANALYSIS_RETRY_BACKOFF_SECONDS", 1.5)), 0.0)
    for attempt in range(1, max_retries + 2):
        try:
            workspace_dir, source_dir, total_files, validation_warnings, temp_ctx = _prepare_workspace(
                source_name=source_name,
                source_bytes=source_bytes,
                input_type=input_type,
                run_id=run_id,
            )
            try:
                analysis_result = run_local_analysis(source_dir=source_dir, workspace_dir=workspace_dir)
            finally:
                temp_ctx.cleanup()

            AnalysisFinding.objects.filter(run=run).delete()
            warning_findings = [
                AnalysisFinding(
                    run=run,
                    tool="validator",
                    severity="LOW",
                    rule="input:skipped_file",
                    issue_key=f"validator:skip:{idx}",
                    issue_status="OPEN",
                    file_path="",
                    line=None,
                    message=warning,
                    message_es=warning,
                    finding_type="CODE_SMELL",
                    effort_minutes=None,
                )
                for idx, warning in enumerate(validation_warnings, start=1)
            ]
            AnalysisFinding.objects.bulk_create(
                warning_findings
                + [
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
                        message_es=translate_finding_message(
                            rule=finding.rule,
                            message=finding.message,
                            tool=finding.tool,
                        ),
                        finding_type=finding.finding_type,
                        effort_minutes=finding.effort_minutes,
                    )
                    for finding in analysis_result.findings
                ]
            )

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
                        big_o_hint=item.big_o_hint,
                        big_o_reason=item.big_o_reason,
                    )
                    for item in analysis_result.syntax_metrics.files
                ]
            )
            _save_done_state(run, analysis_result=analysis_result, total_files=total_files)
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
            )
            return


def _mark_run_started(run: AnalysisRun) -> None:
    run.status = AnalysisRunStatus.RUNNING
    run.started_at = datetime.now(timezone.utc)
    run.error_summary = ""
    run.error_detail = ""
    update_fields = ["status", "started_at", "error_summary", "error_detail"]
    if hasattr(run, "updated_at"):
        update_fields.append("updated_at")
    run.save(update_fields=update_fields)


def _persist_retry_state(
    run: AnalysisRun,
    *,
    attempt: int,
    total_attempts: int,
    trace: str,
    retry_backoff_seconds: float,
) -> None:
    run.error_summary = (f"Intento {attempt} de {total_attempts} falló. Reintentando análisis...")[:255]
    run.error_detail = trace
    run.save(update_fields=["error_summary", "error_detail"])
    sleep_seconds = retry_backoff_seconds * attempt
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)


def _persist_failed_run_state(
    run: AnalysisRun,
    *,
    exc: Exception,
    trace: str,
) -> None:
    run.status = AnalysisRunStatus.FAILED
    run.finished_at = datetime.now(timezone.utc)
    run.error_summary = str(exc)[:255]
    run.error_detail = trace
    run.save(update_fields=["status", "finished_at", "error_summary", "error_detail"])


def _extract_zip(zip_path: Path, target_dir: Path, validation_warnings: list[str] | None = None) -> int:
    max_files = settings.ANALYSIS_MAX_EXTRACTED_FILES
    max_bytes = settings.ANALYSIS_MAX_EXTRACTED_BYTES
    max_entries = int(getattr(settings, "ANALYSIS_MAX_ZIP_ENTRIES", 2000))
    max_depth = int(getattr(settings, "ANALYSIS_MAX_ZIP_PATH_DEPTH", 12))
    max_compression_ratio = float(getattr(settings, "ANALYSIS_MAX_ZIP_COMPRESSION_RATIO", 100.0))
    max_entry_bytes = int(getattr(settings, "ANALYSIS_MAX_ZIP_ENTRY_BYTES", max_bytes))

    extracted_count = 0
    extracted_size = 0
    processed_entries = 0
    collected_warnings: list[str] = []
    with zipfile.ZipFile(zip_path, "r") as archive:
        for member in archive.infolist():
            processed_entries += 1
            if processed_entries > max_entries:
                raise RuntimeError("ZIP inválido: excede el número máximo de entradas permitidas.")
            clean_parts = _validate_zip_member(
                member,
                max_depth=max_depth,
                max_entry_bytes=max_entry_bytes,
                max_compression_ratio=max_compression_ratio,
            )
            if clean_parts is None:
                continue
            content = archive.read(member)
            if len(content) != int(member.file_size):
                raise RuntimeError("ZIP inválido: tamaño real de archivo no coincide con metadatos.")
            try:
                validate_java_source_bytes(content, source_name=member.filename or "archivo.java")
            except ValueError as exc:
                warning = str(exc)
                collected_warnings.append(warning)
                if validation_warnings is not None:
                    validation_warnings.append(warning)
                continue
            extracted_count, extracted_size = _check_extraction_limits(
                extracted_count=extracted_count,
                extracted_size=extracted_size,
                file_size=int(member.file_size),
                max_files=max_files,
                max_bytes=max_bytes,
            )

            destination = _safe_destination_path(target_dir, clean_parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    if extracted_count == 0:
        if collected_warnings:
            raise RuntimeError(
                "No se encontraron archivos .java analizables en el ZIP. "
                f"Primer archivo omitido: {collected_warnings[0]}"
            )
        raise RuntimeError("No se encontraron archivos .java en el ZIP.")
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
        raise RuntimeError("ZIP inválido: contiene entradas no permitidas (enlace/sistema).")
    member_path = _normalize_zip_member_path(member.filename)
    clean_parts = [part for part in member_path.parts if part and part != "."]
    if _has_unsafe_path_parts(clean_parts):
        raise RuntimeError("ZIP inválido: ruta insegura detectada.")
    if "__MACOSX" in clean_parts or member_path.name.startswith("._"):
        return None
    if len(clean_parts) > max_depth:
        raise RuntimeError("ZIP inválido: la profundidad de rutas excede el máximo permitido.")
    if member_path.suffix.lower() == ".zip":
        raise RuntimeError("ZIP inválido: no se permiten archivos ZIP anidados.")
    if member_path.suffix.lower() != ".java":
        return None
    if member.file_size > max_entry_bytes:
        raise RuntimeError("ZIP inválido: un archivo excede el tamaño máximo permitido.")
    compression_ratio = _compression_ratio(member)
    if compression_ratio > max_compression_ratio:
        raise RuntimeError("ZIP inválido: relación de compresión sospechosa detectada.")
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
        raise RuntimeError("ZIP excede el número máximo de archivos permitidos.")
    new_size = extracted_size + file_size
    if new_size > max_bytes:
        raise RuntimeError("ZIP excede el tamaño máximo permitido para extracción.")
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
        return float("inf")
    return file_size / compressed_size


def _normalize_zip_member_path(raw_name: str) -> PurePosixPath:
    normalized_name = str(raw_name or "").replace("\\", "/").strip()
    return PurePosixPath(normalized_name)


def _has_unsafe_path_parts(parts: list[str]) -> bool:
    if not parts:
        return True
    for part in parts:
        if part in ("", ".", ".."):
            return True
        if ":" in part:
            return True
    return False


def _safe_destination_path(target_dir: Path, clean_parts: list[str]) -> Path:
    destination = target_dir.joinpath(*clean_parts)
    resolved_target = target_dir.resolve()
    resolved_destination = destination.resolve()
    try:
        resolved_destination.relative_to(resolved_target)
    except ValueError:
        raise RuntimeError("ZIP inválido: ruta insegura detectada.")
    return destination


def _normalize_file_path(raw_path: str) -> str:
    normalized = (raw_path or "").replace("\\", "/")
    marker = "/source/"
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return Path(normalized).name if normalized else ""
