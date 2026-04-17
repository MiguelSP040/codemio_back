from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
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
        self.admin_user = Usuario.objects.create(
            correo='admin@example.com',
            sub_cognito='sub-admin',
            rol=RolUsuario.ADMIN,
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
        self.assertEqual(run.logical_filename, 'demo.java')
        self.assertTrue(run.is_active_for_filename)
        mocked_start.assert_called_once()

    @patch('analysis.serializers.start_analysis_run')
    def test_create_run_overwrites_active_run_with_same_name_in_same_project(self, mocked_start):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        first = SimpleUploadedFile('Demo.java', b'class DemoV1 {}', content_type='text/plain')
        second = SimpleUploadedFile('demo.java', b'class DemoV2 {}', content_type='text/plain')

        first_response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': first},
            format='multipart',
        )
        self.assertEqual(first_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertFalse(first_response.data.get('overwrite_applied'))

        second_response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': second},
            format='multipart',
        )
        self.assertEqual(second_response.status_code, status.HTTP_202_ACCEPTED)
        self.assertTrue(second_response.data.get('overwrite_applied'))

        runs = list(AnalysisRun.objects.filter(project=self.owner_project, logical_filename='demo.java').order_by('id'))
        self.assertEqual(len(runs), 2)
        self.assertFalse(runs[0].is_active_for_filename)
        self.assertTrue(runs[1].is_active_for_filename)

    @patch('analysis.serializers.start_analysis_run')
    def test_create_run_same_name_in_different_project_keeps_each_active(self, mocked_start):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        own_uploaded = SimpleUploadedFile('shared.java', b'class SharedOwner {}', content_type='text/plain')
        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': own_uploaded},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        AnalysisRun.objects.create(
            project=self.other_project,
            user=self.other_user,
            status=AnalysisRunStatus.DONE,
            input_type='java',
            original_filename='shared.java',
            logical_filename='shared.java',
            is_active_for_filename=True,
        )
        self.assertEqual(
            AnalysisRun.objects.filter(logical_filename='shared.java', is_active_for_filename=True).count(),
            2,
        )

    def test_create_run_rejects_file_type(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        uploaded = SimpleUploadedFile('demo.txt', b'hello', content_type='text/plain')
        response = self.client.post(
            '/analysis/runs/',
            {'project_id': self.owner_project.id, 'source_file': uploaded},
            format='multipart',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('source_file', response.data)

    def test_create_run_rejects_invalid_zip_signature(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        uploaded = SimpleUploadedFile('demo.zip', b'not-a-real-zip', content_type='application/zip')
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

    def test_list_runs_supports_status_filter(self):
        done_run = AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type='java',
            original_filename='done.java',
        )
        AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            status=AnalysisRunStatus.FAILED,
            input_type='java',
            original_filename='failed.java',
        )

        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/analysis/runs/', {'status': 'DONE'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], done_run.id)

    def test_list_runs_supports_active_only_filter(self):
        inactive_run = AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type='java',
            original_filename='demo.java',
            logical_filename='demo.java',
            is_active_for_filename=False,
        )
        active_run = AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type='java',
            original_filename='demo.java',
            logical_filename='demo.java',
            is_active_for_filename=True,
        )
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/analysis/runs/', {'active_only': 'true'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item['id'] for item in response.data['results']}
        self.assertIn(active_run.id, ids)
        self.assertNotIn(inactive_run.id, ids)

    def test_admin_can_list_and_retrieve_foreign_runs(self):
        owner_run = AnalysisRun.objects.create(
            project=self.owner_project,
            user=self.owner,
            input_type='java',
            original_filename='owner.java',
        )
        foreign_run = AnalysisRun.objects.create(
            project=self.other_project,
            user=self.other_user,
            input_type='java',
            original_filename='other.java',
        )
        self.client.force_authenticate(user=CognitoPrincipal(self.admin_user))

        response = self.client.get('/analysis/runs/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item['id'] for item in response.data['results']}
        self.assertIn(owner_run.id, ids)
        self.assertIn(foreign_run.id, ids)

        detail = self.client.get(f'/analysis/runs/{foreign_run.id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['id'], foreign_run.id)
