from unittest.mock import patch

from django.test import TestCase, override_settings

from analysis.models import AnalysisInputType, AnalysisRun, AnalysisRunStatus
from analysis.services.pipeline import _execute_analysis_run, start_analysis_run
from authentication.models import RolUsuario, Usuario
from projects.models import Project


class PipelineQueueControlTests(TestCase):
    def setUp(self):
        self.user = Usuario.objects.create(
            correo='queue-owner@example.com',
            sub_cognito='queue-owner-sub',
            rol=RolUsuario.USER,
        )
        self.project = Project.objects.create(user=self.user, name='Queue Project')

    @patch('analysis.services.pipeline._INFLIGHT_SEMAPHORE.acquire', return_value=False)
    def test_start_analysis_run_marks_failed_when_queue_is_saturated(self, _mocked_acquire):
        run = AnalysisRun.objects.create(
            project=self.project,
            user=self.user,
            input_type=AnalysisInputType.JAVA,
            original_filename='Queue.java',
        )

        start_analysis_run(
            run_id=run.id,
            source_name='Queue.java',
            source_bytes=b'class Queue {}',
            input_type=AnalysisInputType.JAVA,
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AnalysisRunStatus.FAILED)
        self.assertIn('Cola de análisis saturada', run.error_summary)
        self.assertEqual(run.error_detail, 'analysis_queue_overloaded')

    @override_settings(ANALYSIS_RETRY_ATTEMPTS=2, ANALYSIS_RETRY_BACKOFF_SECONDS=0)
    @patch('analysis.services.pipeline.time.sleep', return_value=None)
    @patch('analysis.services.pipeline.push_sonar_scan_only')
    def test_execute_analysis_run_retries_and_succeeds(self, mocked_push, _mocked_sleep):
        run = AnalysisRun.objects.create(
            project=self.project,
            user=self.user,
            input_type=AnalysisInputType.JAVA,
            original_filename='Retry.java',
        )
        mocked_push.side_effect = [
            RuntimeError('sonar transient error'),
            None,
        ]

        _execute_analysis_run(
            run_id=run.id,
            source_name='Retry.java',
            source_bytes=b'class Retry {}',
            input_type=AnalysisInputType.JAVA,
        )

        run.refresh_from_db()
        self.assertEqual(run.status, AnalysisRunStatus.WAITING_SONAR_WEBHOOK)
        self.assertEqual(mocked_push.call_count, 2)
        self.assertEqual(run.error_summary, '')
