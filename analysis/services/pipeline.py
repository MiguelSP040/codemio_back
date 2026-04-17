import traceback
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
import zipfile
from django.conf import settings
from analysis.models import AnalysisFinding, AnalysisInputType, AnalysisRun, AnalysisRunStatus
from analysis.services.message_catalog import get_message_es
from analysis.services.pmd_analyzer import PmdAnalyzer
from analysis.services.spotbugs_analyzer import SpotBugsAnalyzer
from analysis.services.types import NormalizedFinding


_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def start_analysis_run(
    *,
    run_id: int,
    source_name: str,
    source_bytes: bytes,
    input_type: str,
) -> None:
    _EXECUTOR.submit(
        _execute_analysis_run,
        run_id,
        source_name,
        source_bytes,
        input_type,
    )


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

            findings: list[NormalizedFinding] = []
            analyzers = [PmdAnalyzer(), SpotBugsAnalyzer()]
            for analyzer in analyzers:
                findings.extend(analyzer.analyze(source_dir=source_dir, workspace_dir=workspace_dir))

            AnalysisFinding.objects.filter(run=run).delete()
            AnalysisFinding.objects.bulk_create(
                [
                    AnalysisFinding(
                        run=run,
                        tool=finding.tool,
                        severity=finding.severity,
                        rule=finding.rule,
                        file_path=_normalize_file_path(finding.file_path),
                        line=finding.line,
                        message=finding.message,
                        message_es=get_message_es(
                            tool=finding.tool,
                            rule=finding.rule,
                            default_message=finding.message,
                        ),
                    )
                    for finding in findings
                ]
            )

            run.status = AnalysisRunStatus.DONE
            run.total_files_analyzed = total_files
            run.findings_count = len(findings)
            run.finished_at = datetime.now(timezone.utc)
            run.save(update_fields=['status', 'total_files_analyzed', 'findings_count', 'finished_at'])
    except Exception as exc:
        run.status = AnalysisRunStatus.FAILED
        run.finished_at = datetime.now(timezone.utc)
        run.error_summary = str(exc)[:255]
        run.error_detail = traceback.format_exc(limit=10)
        run.save(update_fields=['status', 'finished_at', 'error_summary', 'error_detail'])


def _extract_zip(zip_path: Path, target_dir: Path) -> int:
    max_files = settings.ANALYSIS_MAX_EXTRACTED_FILES
    max_bytes = settings.ANALYSIS_MAX_EXTRACTED_BYTES

    extracted_count = 0
    extracted_size = 0
    with zipfile.ZipFile(zip_path, 'r') as archive:
        for member in archive.infolist():
            if member.is_dir():
                continue
            member_path = PurePosixPath(member.filename)
            if member_path.is_absolute() or '..' in member_path.parts:
                raise RuntimeError('ZIP inválido: ruta insegura detectada.')
            if member_path.suffix.lower() != '.java':
                continue
            extracted_count += 1
            if extracted_count > max_files:
                raise RuntimeError('ZIP excede el número máximo de archivos permitidos.')

            content = archive.read(member)
            extracted_size += len(content)
            if extracted_size > max_bytes:
                raise RuntimeError('ZIP excede el tamaño máximo permitido para extracción.')

            destination = target_dir / Path(member.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)

    if extracted_count == 0:
        raise RuntimeError('No se encontraron archivos .java en el ZIP.')
    return extracted_count


def _normalize_file_path(raw_path: str) -> str:
    normalized = (raw_path or '').replace('\\', '/')
    marker = '/source/'
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return Path(normalized).name if normalized else ''
