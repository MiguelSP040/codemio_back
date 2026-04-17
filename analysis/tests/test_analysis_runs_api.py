from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework import status
from rest_framework.test import APIClient
from analysis.models import AnalysisRun, AnalysisRunStatus
from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal
from projects.models import Project


class AnalysisRunsApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = Usuario.objects.create(
            correo='owner@example.com',
            sub_cognito='sub-owner',
            rol=RolUsuario.USER,
        )
        self.other_user = Usuario.objects.create(
            correo='other@example.com',
            sub_cognito='sub-other',
            rol=RolUsuario.USER,
        )
        self.owner_project = Project.objects.create(user=self.owner, name='Owner Project')
        self.other_project = Project.objects.create(user=self.other_user, name='Other Project')

    def test_create_run_requires_authentication(self):
        uploaded = SimpleUploadedFile('demo.java', b'class Demo {}', content_type='text/plain')
        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': uploaded},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('analysis.serializers.start_analysis_run')
    def test_create_run_accepts_java_and_dispatches_async(self, mocked_start):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        uploaded = SimpleUploadedFile('demo.java', b'class Demo {}', content_type='text/plain')

        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': uploaded},
            format='multipart',
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(AnalysisRun.objects.count(), 1)
        run = AnalysisRun.objects.get()
        self.assertEqual(run.status, AnalysisRunStatus.PENDING)
        self.assertEqual(run.project_id, self.owner_project.id)
        self.assertEqual(run.user_id, self.owner.id)
        mocked_start.assert_called_once()

    def test_create_run_rejects_file_type(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        for filename in ('demo.txt', 'demo.py', 'demo.jar'):
            with self.subTest(filename=filename):
                uploaded = SimpleUploadedFile(filename, b'hello', content_type='application/octet-stream')
                response = self.client.post(
                    '/analysis/runs/',
                    {'project_id': self.owner_project.id, 'source_file': uploaded},
                    format='multipart',
                )
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertIn('source_file', response.data)

    def test_create_run_rejects_non_utf8_java_file(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        uploaded = SimpleUploadedFile('demo.java', b'\xff\xfe\xfd', content_type='application/octet-stream')
        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': uploaded},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('source_file', response.data)

    @override_settings(ANALYSIS_MAX_UPLOAD_BYTES=10)
    def test_create_run_rejects_upload_when_size_exceeds_limit(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        uploaded = SimpleUploadedFile('demo.java', b'class DemoTooLarge {}', content_type='text/plain')
        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': uploaded},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('source_file', response.data)

    def test_create_run_rejects_foreign_project(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        uploaded = SimpleUploadedFile('demo.java', b'class Demo {}', content_type='text/plain')
        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.other_project.id, 'source_file': uploaded},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('project_id', response.data)

    def test_list_runs_returns_only_owner_runs(self):
        own_run = AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            input_type='java',
            original_filename='owner.java',
        )
        AnalysisRun.objects.create(
            project=self.other_project,
            user=self.other_user,
            input_type='java',
            original_filename='other.java',
        )

        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/analysis/runs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], own_run.id)

    def test_list_runs_with_foreign_project_filter_returns_no_data(self):
        AnalysisRun.objects.create(
            project=self.other_project,
            user=self.other_user,
            input_type='java',
            original_filename='other.java',
        )
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get(f'/analysis/runs/?project_id={self.other_project.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 0)

    def test_retrieve_run_blocks_foreign_user(self):
        foreign_run = AnalysisRun.objects.create(
            project=self.other_project,
            user=self.other_user,
            input_type='java',
            original_filename='other.java',
        )
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get(f'/analysis/runs/{foreign_run.id}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @override_settings(DEBUG=False)
    def test_error_detail_is_hidden_in_production_mode(self):
        run = AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            status=AnalysisRunStatus.FAILED,
            input_type='java',
            original_filename='demo.java',
            error_summary='Error corto',
            error_detail='stack trace sensible',
        )
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get(f'/analysis/runs/{run.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['error_summary'], 'Error corto')
        self.assertEqual(response.data['error_detail'], '')
