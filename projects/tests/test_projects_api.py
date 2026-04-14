from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient
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
