from django.urls import path
from analysis.views import AnalysisRunDetailView, AnalysisRunListCreateView

urlpatterns = [
    path('runs/', AnalysisRunListCreateView.as_view(), name='analysis-runs-list-create'),
    path('runs/<int:pk>/', AnalysisRunDetailView.as_view(), name='analysis-runs-detail'),
]
