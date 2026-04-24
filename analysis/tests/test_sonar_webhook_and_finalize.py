import hashlib
import hmac
import json
import unittest
from unittest.mock import patch
from django.db import IntegrityError
from django.test import Client, TestCase, override_settings
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from analysis.models import AnalysisFinding, AnalysisRun, AnalysisRunStatus, SonarWebhookReceipt
from analysis.services.sonar_finalize_service import finalize_analysis_run_from_sonar_api
from analysis.services.sonar_webhook import process_sonar_webhook_request, verify_sonar_webhook_signature
from analysis.services.types import NormalizedFinding, SonarMetrics
from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal
from projects.models import Project

def _hmac_hex(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()

@override_settings(SONAR_WEBHOOK_SECRET='codemio-webhook-secret-32bytes!!')
@unittest.skip("Sonar webhook flow removed: local static analysis is synchronous.")
class SonarWebhookHmacTests(TestCase):
    def test_verify_hmac_accepts_valid_hex(self):
        body = b'{"hello":1}'
        sig = _hmac_hex('codemio-webhook-secret-32bytes!!', body)
        self.assertTrue(
            verify_sonar_webhook_signature(
                body=body,
                signature_header=sig,
                secret='codemio-webhook-secret-32bytes!!',
            )
        )

    def test_verify_hmac_rejects_bad_secret(self):
        body = b'{}'
        sig = _hmac_hex('codemio-webhook-secret-32bytes!!', body)
        self.assertFalse(
            verify_sonar_webhook_signature(
                body=body,
                signature_header=sig,
                secret='wrong-secret-------------------',
            )
        )

    def test_verify_hmac_accepts_sha256_prefix(self):
        body = b'{}'
        sig = 'sha256=' + _hmac_hex('codemio-webhook-secret-32bytes!!', body)
        self.assertTrue(
            verify_sonar_webhook_signature(
                body=body,
                signature_header=sig,
                secret='codemio-webhook-secret-32bytes!!',
            )
        )


@override_settings(SONAR_WEBHOOK_SECRET='codemio-webhook-secret-32bytes!!')
@unittest.skip("Sonar webhook flow removed: local static analysis is synchronous.")
class SonarWebhookIntegrationTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create(
            correo='hook@example.com',
            sub_cognito='hook-sub',
            rol=RolUsuario.USER,
        )
        self.project = Project.objects.create(user=self.user, name='Hook Project')
        self.run = AnalysisRun.objects.create(
            project=self.project,
            user=self.user,
            status=AnalysisRunStatus.WAITING_SONAR_WEBHOOK,
            input_type='java',
            original_filename='Main.java',
            logical_filename='main.java',
            sonar_project_key='',
        )
        self.sonar_key = f'codemio-runtime-{self.run.id}'
        self.run.sonar_project_key = self.sonar_key
        self.run.save(update_fields=['sonar_project_key'])

    @patch('analysis.services.sonar_webhook._schedule_finalize')
    def test_webhook_valid_hmac_enqueues_finalize_and_dedupes(self, mock_schedule):
        body = json.dumps(
            {
                'project': {'key': self.sonar_key},
                'taskId': 'task-abc',
                'analysedAt': '2024-06-01T12:00:00Z',
            }
        ).encode('utf-8')
        sig = _hmac_hex('codemio-webhook-secret-32bytes!!', body)
        raw_client = Client()
        r1 = raw_client.post(
            '/analysis/webhooks/sonar/',
            data=body,
            content_type='application/json',
            HTTP_X_SONAR_WEBHOOK_HMAC_SHA256=sig,
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        mock_schedule.assert_called_once()
        self.run.refresh_from_db()
        self.assertEqual(self.run.sonar_task_id, 'task-abc')

        r2 = raw_client.post(
            '/analysis/webhooks/sonar/',
            data=body,
            content_type='application/json',
            HTTP_X_SONAR_WEBHOOK_HMAC_SHA256=sig,
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(
            json.loads(r2.content.decode())['detail'],
            'duplicate_delivery_refinalize_scheduled',
        )
        self.assertEqual(SonarWebhookReceipt.objects.count(), 1)
        self.assertEqual(mock_schedule.call_count, 2)

    @patch('analysis.services.sonar_webhook._schedule_finalize')
    def test_duplicate_webhook_does_not_reschedule_when_run_already_finalized(self, mock_schedule):
        body = json.dumps(
            {
                'project': {'key': self.sonar_key},
                'taskId': 'task-abc',
                'analysedAt': '2024-06-01T12:00:00Z',
            }
        ).encode('utf-8')
        sig = _hmac_hex('codemio-webhook-secret-32bytes!!', body)
        raw_client = Client()
        r1 = raw_client.post(
            '/analysis/webhooks/sonar/',
            data=body,
            content_type='application/json',
            HTTP_X_SONAR_WEBHOOK_HMAC_SHA256=sig,
        )
        self.assertEqual(r1.status_code, status.HTTP_200_OK)
        mock_schedule.assert_called_once()

        self.run.status = AnalysisRunStatus.DONE
        self.run.last_sonar_sync_at = timezone.now()
        self.run.save(update_fields=['status', 'last_sonar_sync_at'])

        r2 = raw_client.post(
            '/analysis/webhooks/sonar/',
            data=body,
            content_type='application/json',
            HTTP_X_SONAR_WEBHOOK_HMAC_SHA256=sig,
        )
        self.assertEqual(r2.status_code, status.HTTP_200_OK)
        self.assertEqual(json.loads(r2.content.decode())['detail'], 'duplicate_delivery')
        mock_schedule.assert_called_once()

    def test_webhook_rejects_invalid_hmac(self):
        body = json.dumps({'project': {'key': self.sonar_key}}).encode('utf-8')
        raw_client = Client()
        response = raw_client.post(
            '/analysis/webhooks/sonar/',
            data=body,
            content_type='application/json',
            HTTP_X_SONAR_WEBHOOK_HMAC_SHA256='deadbeef',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


@unittest.skip("Sonar finalize flow removed: local static analysis is synchronous.")
class SonarFinalizeServiceTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create(
            correo='fin@example.com',
            sub_cognito='fin-sub',
            rol=RolUsuario.USER,
        )
        self.project = Project.objects.create(user=self.user, name='Fin Project')
        self.run = AnalysisRun.objects.create(
            project=self.project,
            user=self.user,
            status=AnalysisRunStatus.WAITING_SONAR_WEBHOOK,
            input_type='java',
            original_filename='X.java',
            logical_filename='x.java',
            sonar_project_key='',
        )
        self.sonar_key = f'codemio-runtime-{self.run.id}'
        self.run.sonar_project_key = self.sonar_key
        self.run.save(update_fields=['sonar_project_key'])

    @patch('analysis.services.sonar_finalize_service.fetch_sonar_metrics_public')
    @patch('analysis.services.sonar_finalize_service.fetch_sonar_issues_public')
    def test_finalize_writes_findings_and_sets_done(self, mock_issues, mock_metrics):
        mock_issues.return_value = [
            NormalizedFinding(
                tool='sonarcloud',
                severity='HIGH',
                rule='java:S1',
                issue_key='k1',
                issue_status='OPEN',
                file_path='src/A.java',
                line=3,
                message='problem',
                finding_type='BUG',
                effort_minutes=5,
            )
        ]
        mock_metrics.return_value = SonarMetrics(
            quality_gate_status='FAILED',
            bugs=1,
            vulnerabilities=0,
            code_smells=0,
            complexity=1,
            duplicated_lines_density=0.0,
            duplicated_lines=0,
            coverage=0.0,
            lines_to_cover=1,
            ncloc=5,
            reliability_rating=1,
            security_rating=1,
            maintainability_rating=1,
        )
        ok = finalize_analysis_run_from_sonar_api(self.run.id, webhook_task_id='t1', webhook_analysed_at='d1')
        self.assertTrue(ok)
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, AnalysisRunStatus.DONE)
        self.assertEqual(self.run.findings_count, 1)
        self.assertEqual(AnalysisFinding.objects.filter(run=self.run).count(), 1)

    @patch('analysis.services.sonar_finalize_service.fetch_sonar_metrics_public')
    @patch('analysis.services.sonar_finalize_service.fetch_sonar_issues_public')
    def test_finalize_idempotent_when_already_done(self, mock_issues, mock_metrics):
        self.run.status = AnalysisRunStatus.DONE
        self.run.save(update_fields=['status'])
        ok = finalize_analysis_run_from_sonar_api(self.run.id)
        self.assertFalse(ok)
        mock_issues.assert_not_called()
        mock_metrics.assert_not_called()


@override_settings(SONAR_WEBHOOK_SECRET='')
@unittest.skip("Sonar webhook flow removed: local static analysis is synchronous.")
class SonarWebhookSecretMissingTests(TestCase):
    def test_process_returns_503_without_secret(self):
        code, msg = process_sonar_webhook_request(body=b'{}', signature_header='abc')
        self.assertEqual(code, 503)
        self.assertEqual(msg, 'webhook_secret_missing')


@unittest.skip("Sonar webhook flow removed: local static analysis is synchronous.")
class SonarWebhookReceiptModelTests(TestCase):
    def test_duplicate_payload_sha_raises_integrity(self):
        SonarWebhookReceipt.objects.create(payload_sha256='a' * 64, project_key='p')
        with self.assertRaises(IntegrityError):
            SonarWebhookReceipt.objects.create(payload_sha256='a' * 64, project_key='q')


class StatusBulkAuthTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create(
            correo='bulk@example.com',
            sub_cognito='bulk-sub',
            rol=RolUsuario.USER,
        )
        self.project = Project.objects.create(user=self.user, name='Bulk')
        self.run = AnalysisRun.objects.create(
            project=self.project,
            user=self.user,
            status=AnalysisRunStatus.RUNNING,
            input_type='java',
            original_filename='z.java',
        )

    def test_status_bulk_requires_auth(self):
        client = APIClient()
        r = client.get('/analysis/runs/status_bulk/', {'ids': str(self.run.id)})
        self.assertEqual(r.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_status_bulk_returns_data_for_owner(self):
        client = APIClient()
        client.force_authenticate(user=CognitoPrincipal(self.user))
        r = client.get('/analysis/runs/status_bulk/', {'ids': str(self.run.id)})
        self.assertEqual(r.status_code, status.HTTP_200_OK)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]['id'], self.run.id)
