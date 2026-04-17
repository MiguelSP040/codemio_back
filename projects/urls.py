from django.urls import path
from projects.views import ProjectDetailView, ProjectListCreateView


urlpatterns = [
    path('', ProjectListCreateView.as_view(), name='projects-list-create'),
    path('<int:pk>/', ProjectDetailView.as_view(), name='projects-detail'),
]
