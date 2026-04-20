from __future__ import annotations
import hashlib
import hmac
import json
import logging
import threading
from typing import Any
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone
from analysis.instrumentation import analysis_instr_log, digest_prefix
from analysis.models import AnalysisRun, AnalysisRunStatus, SonarWebhookReceipt
from analysis.services.sonar_finalize_service import finalize_analysis_run_from_sonar_api

logger = logging.getLogger(__name__)


def verify_sonar_webhook_signature(*, body: bytes, signature_header: str | None, secret: str) -> bool:
    if not secret:
        return False
    if not signature_header:
        return False
    header = signature_header.strip()
    # SonarCloud: X-Sonar-Webhook-HMAC-SHA256 (hex minúsculas)
    expected = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
    if hmac.compare_digest(expected, header):
        return True
    # Algunas integraciones envían prefijo "sha256="
    alt = header.removeprefix('sha256=').strip()
    return hmac.compare_digest(expected, alt)


def _parse_json_body(body: bytes) -> dict[str, Any]:
    try:
        raw = json.loads(body.decode('utf-8') or '{}')
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def _extract_project_key(payload: dict[str, Any]) -> str:
    project = payload.get('project')
    if isinstance(project, dict):
        return str(project.get('key') or '').strip()
    return ''


def _extract_task_id(payload: dict[str, Any]) -> str:
    return str(payload.get('taskId') or payload.get('task_id') or '').strip()


def _extract_analysed_at(payload: dict[str, Any]) -> str:
    return str(payload.get('analysedAt') or payload.get('analysed_at') or '').strip()


def _find_open_run_for_project_key(project_key: str) -> AnalysisRun | None:
    if not project_key:
        return None
    return (
        AnalysisRun.objects.filter(
            sonar_project_key=project_key,
            status=AnalysisRunStatus.WAITING_SONAR_WEBHOOK,
        )
        .order_by('-id')
        .first()
    )


def _schedule_finalize(
    run_id: int,
    *,
    webhook_task_id: str,
    webhook_analysed_at: str,
    payload_digest: str = '',
) -> None:
    def _job() -> None:
        from django.db import close_old_connections

        close_old_connections()
        try:
            finalize_analysis_run_from_sonar_api(
                run_id,
                webhook_task_id=webhook_task_id,
                webhook_analysed_at=webhook_analysed_at,
            )
        except Exception:
            logger.exception('Background finalize failed run_id=%s', run_id)
        finally:
            close_old_connections()

    transaction.on_commit(lambda: threading.Thread(target=_job, name=f'sonar-finalize-{run_id}', daemon=True).start())
    analysis_instr_log(
        logger,
        'sonar_webhook_finalize_scheduled',
        run_id=run_id,
        sonar_project_key='',
        task_id=(webhook_task_id or '')[:64],
        analysed_at_len=len(webhook_analysed_at or ''),
        digest_prefix=digest_prefix(payload_digest),
        detail='on_commit_thread',
    )


def _handle_duplicate_webhook_delivery(
    *,
    digest: str,
    payload_project_key: str,
    task_id: str,
    analysed_at: str,
) -> tuple[int, str]:
    def _duplicate_ok(detail_reason: str, *, run: AnalysisRun | None = None, key: str = '') -> tuple[int, str]:
        analysis_instr_log(
            logger,
            'sonar_webhook_duplicate',
            digest_prefix=digest_prefix(digest),
            project_key=(key or '')[:120],
            run_id=run.id if run is not None else 0,
            task_id=(task_id or '')[:64],
            analysed_at_len=len(analysed_at or ''),
            detail='duplicate_delivery',
            reason=detail_reason,
            status=run.status if run is not None else '',
        )
        return 200, 'duplicate_delivery'

    def _can_refinalize(run: AnalysisRun, key: str) -> bool:
        if run.status != AnalysisRunStatus.WAITING_SONAR_WEBHOOK:
            _duplicate_ok('run_not_waiting', run=run, key=key)
            return False
        if run.last_sonar_sync_at is not None:
            _duplicate_ok('already_has_last_sonar_sync', run=run, key=key)
            return False
        pk_run = (run.sonar_project_key or '').strip()
        if key and pk_run and key != pk_run:
            logger.warning(
                'Webhook duplicado: project_key no coincide con run digest=%s...',
                digest[:12],
            )
            _duplicate_ok('project_key_mismatch', run=run, key=key)
            return False
        return True

    receipt = (
        SonarWebhookReceipt.objects.select_related('analysis_run')
        .filter(payload_sha256=digest)
        .first()
    )
    if receipt is None:
        logger.warning('Webhook receipt duplicate IntegrityError sin fila digest=%s...', digest[:12])
        return 200, 'duplicate_delivery'

    key = (payload_project_key or receipt.project_key or '').strip()
    run = receipt.analysis_run
    if run is None and key:
        run = _find_open_run_for_project_key(key)
        if run is not None:
            SonarWebhookReceipt.objects.filter(pk=receipt.pk).update(
                analysis_run=run,
                orphan=False,
            )
    if run is None:
        return _duplicate_ok('no_resolved_run', key=key)

    run.refresh_from_db()
    if not _can_refinalize(run, key):
        return 200, 'duplicate_delivery'

    now = timezone.now()
    AnalysisRun.objects.filter(pk=run.id).update(
        webhook_received_at=now,
        sonar_task_id=task_id[:128] if task_id else '',
        sonar_analysis_id=analysed_at[:180] if analysed_at else '',
    )
    _schedule_finalize(
        run.id,
        webhook_task_id=task_id,
        webhook_analysed_at=analysed_at,
        payload_digest=digest,
    )
    analysis_instr_log(
        logger,
        'sonar_webhook_duplicate_refinalize_scheduled',
        digest_prefix=digest_prefix(digest),
        project_key=key[:120],
        run_id=run.id,
        task_id=(task_id or '')[:64],
        analysed_at_len=len(analysed_at or ''),
        detail='duplicate_delivery_refinalize_scheduled',
    )
    return 200, 'duplicate_delivery_refinalize_scheduled'


def process_sonar_webhook_request(*, body: bytes, signature_header: str | None) -> tuple[int, str]:

    secret = str(getattr(settings, 'SONAR_WEBHOOK_SECRET', '') or '').strip()
    if not secret:
        logger.error('SONAR_WEBHOOK_SECRET no configurado; rechazando webhook.')
        return 503, 'webhook_secret_missing'

    if not verify_sonar_webhook_signature(body=body, signature_header=signature_header, secret=secret):
        analysis_instr_log(
            logger,
            'sonar_webhook_invalid_signature',
            body_bytes=len(body),
            detail='invalid_signature',
        )
        return 401, 'invalid_signature'

    digest = hashlib.sha256(body).hexdigest()
    payload = _parse_json_body(body)
    project_key = _extract_project_key(payload)
    task_id = _extract_task_id(payload)
    analysed_at = _extract_analysed_at(payload)
    analysis_instr_log(
        logger,
        'sonar_webhook_received',
        digest_prefix=digest_prefix(digest),
        project_key=project_key[:120],
        task_id=(task_id or '')[:64],
        analysed_at_len=len(analysed_at or ''),
        body_bytes=len(body),
        detail='signature_ok',
    )

    try:
        with transaction.atomic():
            SonarWebhookReceipt.objects.create(
                payload_sha256=digest,
                project_key=project_key,
                orphan=False,
            )
    except IntegrityError:
        return _handle_duplicate_webhook_delivery(
            digest=digest,
            payload_project_key=project_key,
            task_id=task_id,
            analysed_at=analysed_at,
        )

    run = _find_open_run_for_project_key(project_key)
    if run is None:
        SonarWebhookReceipt.objects.filter(payload_sha256=digest).update(orphan=True)
        logger.info('Sonar webhook sin run abierto project_key=%s', project_key)
        analysis_instr_log(
            logger,
            'sonar_webhook_no_matching_run',
            digest_prefix=digest_prefix(digest),
            project_key=project_key[:120],
            task_id=(task_id or '')[:64],
            analysed_at_len=len(analysed_at or ''),
            detail='no_matching_run',
        )
        return 200, 'no_matching_run'

    SonarWebhookReceipt.objects.filter(payload_sha256=digest).update(analysis_run=run, orphan=False)
    now = timezone.now()
    AnalysisRun.objects.filter(pk=run.id).update(
        webhook_received_at=now,
        sonar_task_id=task_id[:128] if task_id else '',
        sonar_analysis_id=analysed_at[:180] if analysed_at else '',
    )

    _schedule_finalize(
        run.id,
        webhook_task_id=task_id,
        webhook_analysed_at=analysed_at,
        payload_digest=digest,
    )
    analysis_instr_log(
        logger,
        'sonar_webhook_accepted',
        digest_prefix=digest_prefix(digest),
        project_key=project_key[:120],
        run_id=run.id,
        task_id=(task_id or '')[:64],
        analysed_at_len=len(analysed_at or ''),
        detail='accepted',
    )
    return 200, 'accepted'
