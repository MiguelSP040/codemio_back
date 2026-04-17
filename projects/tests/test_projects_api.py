from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
from analysis.models import AnalysisFileMetric, AnalysisFinding, AnalysisInputType, AnalysisRun, AnalysisRunStatus
from authentication.models import RolUsuario, Usuario
from authentication.principal import CognitoPrincipal
from projects.models import Project, ProjectState


class ProjectsApiTests(TestCase):
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

    def test_create_project_requires_authentication(self):
        response = self.client.post('/projects/', {'name': 'Proyecto X'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_project_persists_for_authenticated_user(self):
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.post('/projects/', {'name': 'Proyecto A'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Proyecto A')
        self.assertEqual(response.data['user_id'], self.owner.id)
        self.assertEqual(Project.objects.count(), 1)
        project = Project.objects.get()
        self.assertEqual(project.user_id, self.owner.id)
        self.assertEqual(project.state, ProjectState.ACTIVE)
        self.assertIsNone(project.deleted_at)

    def test_create_project_rejects_duplicate_active_name_for_same_user(self):
        Project.objects.create(user=self.owner, name='Proyecto A')
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.post('/projects/', {'name': 'Proyecto A'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_create_project_allows_same_name_if_previous_is_deleted(self):
        Project.objects.create(
            user=self.owner,
            name='Proyecto A',
            state=ProjectState.DELETED,
            deleted_at=timezone.now(),
        )
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.post('/projects/', {'name': 'Proyecto A'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_update_project_rejects_duplicate_active_name_for_same_user(self):
        first = Project.objects.create(user=self.owner, name='Proyecto A')
        second = Project.objects.create(user=self.owner, name='Proyecto B')
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.patch(
            f'/projects/{second.id}/',
            {'name': first.name},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('name', response.data)

    def test_list_projects_returns_only_owner_active_projects(self):
        own_active = Project.objects.create(user=self.owner, name='Owner Active')
        Project.objects.create(
            user=self.owner,
            name='Owner Deleted',
            state=ProjectState.DELETED,
            deleted_at=timezone.now(),
        )
        Project.objects.create(user=self.other_user, name='Other Active')
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['id'], own_active.id)
        self.assertEqual(response.data['results'][0]['name'], own_active.name)

    def test_retrieve_and_update_only_owner_project(self):
        owned = Project.objects.create(user=self.owner, name='Original Name')
        foreign = Project.objects.create(user=self.other_user, name='Other Name')
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))

        retrieve_response = self.client.get(f'/projects/{owned.id}/')
        self.assertEqual(retrieve_response.status_code, status.HTTP_200_OK)
        self.assertEqual(retrieve_response.data['id'], owned.id)

        update_response = self.client.patch(
            f'/projects/{owned.id}/',
            {'name': 'Updated Name'},
            format='json',
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data['name'], 'Updated Name')

        forbidden_response = self.client.get(f'/projects/{foreign.id}/')
        self.assertEqual(forbidden_response.status_code, status.HTTP_404_NOT_FOUND)

    def test_admin_can_list_and_retrieve_foreign_projects(self):
        own = Project.objects.create(user=self.owner, name='Owner Project')
        foreign = Project.objects.create(user=self.other_user, name='Foreign Project')
        self.client.force_authenticate(user=CognitoPrincipal(self.admin_user))

        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = {item['id'] for item in response.data['results']}
        self.assertIn(own.id, ids)
        self.assertIn(foreign.id, ids)

        detail = self.client.get(f'/projects/{foreign.id}/')
        self.assertEqual(detail.status_code, status.HTTP_200_OK)
        self.assertEqual(detail.data['id'], foreign.id)

    def test_admin_cannot_update_or_delete_foreign_project(self):
        foreign = Project.objects.create(user=self.other_user, name='Foreign Project')
        self.client.force_authenticate(user=CognitoPrincipal(self.admin_user))

        update_response = self.client.patch(
            f'/projects/{foreign.id}/',
            {'name': 'Updated by admin'},
            format='json',
        )
        self.assertEqual(update_response.status_code, status.HTTP_403_FORBIDDEN)

        delete_response = self.client.delete(f'/projects/{foreign.id}/')
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_update_and_delete_own_project(self):
        own = Project.objects.create(user=self.admin_user, name='Admin Own Project')
        self.client.force_authenticate(user=CognitoPrincipal(self.admin_user))

        update_response = self.client.patch(
            f'/projects/{own.id}/',
            {'name': 'Admin Own Updated'},
            format='json',
        )
        self.assertEqual(update_response.status_code, status.HTTP_200_OK)
        self.assertEqual(update_response.data['name'], 'Admin Own Updated')

        delete_response = self.client.delete(f'/projects/{own.id}/')
        self.assertEqual(delete_response.status_code, status.HTTP_204_NO_CONTENT)

    def test_delete_project_is_logical(self):
        project = Project.objects.create(user=self.owner, name='Delete Me')
        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.delete(f'/projects/{project.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        project.refresh_from_db()
        self.assertEqual(project.state, ProjectState.DELETED)
        self.assertIsNotNone(project.deleted_at)

        list_response = self.client.get('/projects/')
        self.assertEqual(list_response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(list_response.data['results']), 0)

    def test_projects_include_quality_score_from_latest_done_run_per_file(self):
        project = Project.objects.create(user=self.owner, name='Scored Project')
        other_project = Project.objects.create(user=self.other_user, name='Other Project')

        old_run = AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='old.java',
        )
        new_run = AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='new.java',
        )
        other_run = AnalysisRun.objects.create(
            project=other_project,
            user=self.other_user,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='other.java',
        )

        AnalysisFinding.objects.create(
            run=old_run,
            tool='spotbugs',
            severity='CRITICAL',
            rule='X1',
            file_path='src/A.java',
            line=10,
            message='old critical',
            message_es='old critical',
        )
        AnalysisFinding.objects.create(
            run=old_run,
            tool='pmd',
            severity='HIGH',
            rule='X2',
            file_path='src/B.java',
            line=20,
            message='high issue',
            message_es='high issue',
        )
        AnalysisFinding.objects.create(
            run=new_run,
            tool='pmd',
            severity='MEDIUM',
            rule='X3',
            file_path='src/A.java',
            line=30,
            message='new medium',
            message_es='new medium',
        )
        AnalysisFinding.objects.create(
            run=other_run,
            tool='pmd',
            severity='CRITICAL',
            rule='Y1',
            file_path='src/Other.java',
            line=40,
            message='other critical',
            message_es='other critical',
        )

        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)

        item = response.data['results'][0]
        self.assertEqual(item['id'], project.id)
        self.assertIn('quality_score', item)
        self.assertEqual(item['quality_score'], 98)
        self.assertIn('severity_summary', item)
        self.assertEqual(
            item['severity_summary'],
            {
                'critical': 0,
                'high': 1,
                'medium': 1,
                'low': 0,
                'total': 2,
            },
        )

    def test_quality_score_is_clamped_to_zero(self):
        project = Project.objects.create(user=self.owner, name='Clamp Score Project')
        run = AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='huge.java',
        )

        for idx in range(30):
            AnalysisFinding.objects.create(
                run=run,
                tool='spotbugs',
                severity='CRITICAL',
                rule=f'C{idx}',
                file_path='src/SameFile.java',
                line=1,
                message='critical issue',
                message_es='critical issue',
            )

        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        item = response.data['results'][0]
        self.assertEqual(item['quality_score'], 0)
        self.assertEqual(item['severity_summary']['critical'], 30)

    def test_quality_score_uses_latest_run_for_same_logical_file_with_temp_paths(self):
        project = Project.objects.create(user=self.owner, name='Temp Path Project')
        old_run = AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='old.java',
        )
        new_run = AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='new.java',
        )

        AnalysisFinding.objects.create(
            run=old_run,
            tool='pmd',
            severity='CRITICAL',
            rule='OLD',
            file_path='/tmp/codemio-analysis-1-aaaa/source/TestCalidad.java',
            line=10,
            message='old',
            message_es='old',
        )
        AnalysisFinding.objects.create(
            run=new_run,
            tool='pmd',
            severity='MEDIUM',
            rule='NEW',
            file_path='/tmp/codemio-analysis-2-bbbb/source/TestCalidad.java',
            line=20,
            message='new',
            message_es='new',
        )

        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['results'][0]
        self.assertEqual(item['quality_score'], 99)
        self.assertEqual(
            item['severity_summary'],
            {
                'critical': 0,
                'high': 0,
                'medium': 1,
                'low': 0,
                'total': 1,
            },
        )

    def test_projects_include_syntax_summary_from_active_done_runs(self):
        project = Project.objects.create(user=self.owner, name='Syntax Summary Project')
        active_run = AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='active.java',
            logical_filename='active.java',
            is_active_for_filename=True,
        )
        AnalysisRun.objects.create(
            project=project,
            user=self.owner,
            status=AnalysisRunStatus.DONE,
            input_type=AnalysisInputType.JAVA,
            original_filename='old.java',
            logical_filename='old.java',
            is_active_for_filename=False,
        )
        AnalysisFileMetric.objects.create(
            run=active_run,
            file_path='src/Active.java',
            classes_count=2,
            methods_count=5,
            parameters_count=4,
            inheritance_count=1,
            interclass_calls_count=3,
        )

        self.client.force_authenticate(user=CognitoPrincipal(self.owner))
        response = self.client.get('/projects/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        item = response.data['results'][0]
        self.assertEqual(
            item['syntax_summary'],
            {
                'classes': 2,
                'methods': 5,
                'parameters': 4,
                'inheritance': 1,
                'interclass_calls': 3,
            },
        )
