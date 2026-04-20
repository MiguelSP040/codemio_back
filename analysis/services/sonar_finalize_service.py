from __future__ import annotations
import logging
import time
import traceback
from pathlib import Path
from django.db import transaction
from django.utils import timezone
from analysis.instrumentation import analysis_instr_log
from analysis.models import AnalysisFinding, AnalysisRun, AnalysisRunStatus
from analysis.services.sonar_runtime_service import fetch_sonar_issues_public, fetch_sonar_metrics_public

logger = logging.getLogger(__name__)

def _normalize_file_path(raw_path: str) -> str:
    normalized = (raw_path or '').replace('\\', '/')
    marker = '/source/'
    if marker in normalized:
        return normalized.split(marker, 1)[1]
    return Path(normalized).name if normalized else ''


def _log_finalize_skip(*, run_id: int, t0: float, reason: str, run: AnalysisRun | None = None, webhook_task_id: str = '', findings_count: int = 0) -> None:
    analysis_instr_log(
        logger,
        'sonar_finalize_skipped_not_waiting',
        run_id=run_id,
        sonar_project_key=((run.sonar_project_key if run else '') or '')[:120],
        task_id=(webhook_task_id or '')[:64],
        duration_ms=int((time.perf_counter() - t0) * 1000),
        findings_count=findings_count,
        quality_gate_status='',
        error_type='',
        error_message='',
        reason=reason,
        status=run.status if run is not None else '',
    )


def _persist_final_metrics(run: AnalysisRun, findings, metrics, now, webhook_task_id: str, webhook_analysed_at: str) -> None:
    previous_status = run.status
    run.status = AnalysisRunStatus.DONE
    run.quality_gate_status = metrics.quality_gate_status
    run.bugs = metrics.bugs
    run.vulnerabilities = metrics.vulnerabilities
    run.code_smells = metrics.code_smells
    run.complexity = metrics.complexity
    run.duplicated_lines_density = metrics.duplicated_lines_density
    run.duplicated_lines = metrics.duplicated_lines
    run.coverage = metrics.coverage
    run.lines_to_cover = metrics.lines_to_cover
    run.ncloc = metrics.ncloc
    run.reliability_rating = metrics.reliability_rating
    run.security_rating = metrics.security_rating
    run.maintainability_rating = metrics.maintainability_rating
    run.findings_count = len(findings)
    run.finished_at = now
    run.last_sonar_sync_at = now
    run.error_summary = ''
    run.error_detail = ''
    if webhook_task_id:
        run.sonar_task_id = str(webhook_task_id)[:128]
    if webhook_analysed_at:
        run.sonar_analysis_id = str(webhook_analysed_at)[:180]
    run.save(
        update_fields=[
            'status',
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
            'findings_count',
            'finished_at',
            'last_sonar_sync_at',
            'error_summary',
            'error_detail',
            'sonar_task_id',
            'sonar_analysis_id',
        ]
    )
    logger.info(
        'event=analysis_run_status_transition run_id=%s from_status=%s to_status=%s reason=%s',
        run.id,
        previous_status,
        run.status,
        'sonar_finalize_success',
    )


def _get_waiting_run_or_skip(*, run_id: int, t0: float, webhook_task_id: str) -> AnalysisRun | None:
    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None:
            _log_finalize_skip(run_id=run_id, t0=t0, reason='no_run', webhook_task_id=webhook_task_id)
            return None
        if run.status != AnalysisRunStatus.WAITING_SONAR_WEBHOOK:
            _log_finalize_skip(run_id=run_id, t0=t0, reason='wrong_status', run=run, webhook_task_id=webhook_task_id)
            return None
        if not (run.sonar_project_key or '').strip():
            _log_finalize_skip(run_id=run_id, t0=t0, reason='no_sonar_project_key', run=run, webhook_task_id=webhook_task_id)
            return None
        return run


def _fetch_sonar_payloads(*, run: AnalysisRun, run_id: int, sk: str, t0: float, webhook_task_id: str):
    try:
        findings = fetch_sonar_issues_public(run.sonar_project_key)
        metrics = fetch_sonar_metrics_public(run.sonar_project_key)
        return findings, metrics
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        analysis_instr_log(
            logger,
            'sonar_finalize_fetch_failed',
            run_id=run_id,
            sonar_project_key=sk,
            task_id=(webhook_task_id or '')[:64],
            duration_ms=duration_ms,
            findings_count=0,
            quality_gate_status='',
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
        )
        logger.exception('Sonar API sync failed for run_id=%s', run_id)
        _mark_run_failed_from_sync(run_id, exc)
        return None, None


def finalize_analysis_run_from_sonar_api(
    run_id: int,
    *,
    webhook_task_id: str = '',
    webhook_analysed_at: str = '',
) -> bool:

    t0 = time.perf_counter()
    run = _get_waiting_run_or_skip(run_id=run_id, t0=t0, webhook_task_id=webhook_task_id)
    if run is None:
        return False

    sk = (run.sonar_project_key or '')[:120]
    analysis_instr_log(
        logger,
        'sonar_finalize_started',
        run_id=run_id,
        sonar_project_key=sk,
        task_id=(webhook_task_id or '')[:64],
        duration_ms=int((time.perf_counter() - t0) * 1000),
        findings_count=0,
        quality_gate_status='',
        error_type='',
        error_message='',
    )

    findings, metrics = _fetch_sonar_payloads(
        run=run,
        run_id=run_id,
        sk=sk,
        t0=t0,
        webhook_task_id=webhook_task_id,
    )
    if findings is None or metrics is None:
        return False

    now = timezone.now()
    try:
        with transaction.atomic():
            run = AnalysisRun.objects.select_for_update().filter(pk=run_id).first()
            if run is None or run.status != AnalysisRunStatus.WAITING_SONAR_WEBHOOK:
                _log_finalize_skip(
                    run_id=run_id,
                    t0=t0,
                    reason='race_after_fetch',
                    run=run,
                    webhook_task_id=webhook_task_id,
                    findings_count=len(findings) if findings else 0,
                )
                return False

            AnalysisFinding.objects.filter(run=run).delete()
            if findings:
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

            _persist_final_metrics(
                run,
                findings=findings,
                metrics=metrics,
                now=now,
                webhook_task_id=webhook_task_id,
                webhook_analysed_at=webhook_analysed_at,
            )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        analysis_instr_log(
            logger,
            'sonar_finalize_failed',
            run_id=run_id,
            sonar_project_key=sk,
            task_id=(webhook_task_id or '')[:64],
            duration_ms=duration_ms,
            findings_count=len(findings) if findings else 0,
            quality_gate_status='',
            error_type=type(exc).__name__,
            error_message=str(exc)[:200],
        )
        logger.exception('Persist Sonar results failed for run_id=%s', run_id)
        _mark_run_failed_from_sync(run_id, exc)
        return False

    duration_ms = int((time.perf_counter() - t0) * 1000)
    analysis_instr_log(
        logger,
        'sonar_finalize_done',
        run_id=run_id,
        sonar_project_key=sk,
        task_id=(webhook_task_id or '')[:64],
        duration_ms=duration_ms,
        findings_count=len(findings),
        quality_gate_status=metrics.quality_gate_status,
        error_type='',
        error_message='',
    )
    return True


def _mark_run_failed_from_sync(run_id: int, exc: BaseException) -> None:
    trace = traceback.format_exc(limit=12)
    with transaction.atomic():
        run = AnalysisRun.objects.select_for_update().filter(pk=run_id).first()
        if run is None or run.status != AnalysisRunStatus.WAITING_SONAR_WEBHOOK:
            return
        previous_status = run.status
        run.status = AnalysisRunStatus.FAILED
        run.finished_at = timezone.now()
        run.error_summary = str(exc)[:255]
        run.error_detail = trace
        run.save(update_fields=['status', 'finished_at', 'error_summary', 'error_detail'])
        logger.info(
            'event=analysis_run_status_transition run_id=%s from_status=%s to_status=%s reason=%s error_summary=%s',
            run.id,
            previous_status,
            run.status,
            'sonar_finalize_failed',
            run.error_summary,
        )


def reconcile_stale_waiting_runs(*, max_runs: int = 20) -> int:

    from datetime import timedelta
    from django.conf import settings

    minutes = int(getattr(settings, 'SONAR_WEBHOOK_STALE_MINUTES', 45) or 45)
    threshold = timezone.now() - timedelta(minutes=max(minutes, 5))
    qs = (
        AnalysisRun.objects.filter(
            status=AnalysisRunStatus.WAITING_SONAR_WEBHOOK,
            started_at__isnull=False,
            started_at__lt=threshold,
        )
        .exclude(sonar_project_key='')
        .order_by('started_at')[:max_runs]
    )
    runs = list(qs)
    analysis_instr_log(
        logger,
        'sonar_reconcile_started',
        candidate_count=len(runs),
        max_runs=max_runs,
        stale_minutes=minutes,
        threshold_iso=threshold.isoformat(),
    )
    fixed = 0
    for run in runs:
        analysis_instr_log(
            logger,
            'sonar_reconcile_candidate',
            run_id=run.id,
            project_id=run.project_id,
            sonar_project_key=(run.sonar_project_key or '')[:120],
            started_at_iso=run.started_at.isoformat() if run.started_at else '',
        )
        if finalize_analysis_run_from_sonar_api(run.id):
            fixed += 1
            analysis_instr_log(logger, 'sonar_reconcile_recovered', run_id=run.id)
        else:
            analysis_instr_log(logger, 'sonar_reconcile_failed', run_id=run.id)
    analysis_instr_log(
        logger,
        'sonar_reconcile_finished',
        candidate_count=len(runs),
        recovered_count=fixed,
    )
    return fixed
