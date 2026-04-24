from django.urls import path
from analysis.views import (
    AnalysisRunDetailView,
    AnalysisRunListCreateView,
    AnalysisRunStatusBulkView,
    AnalysisRunStatusView,
)

urlpatterns = [
    path('runs/', AnalysisRunListCreateView.as_view(), name='analysis-runs-list-create'),
    path('runs/status_bulk/', AnalysisRunStatusBulkView.as_view(), name='analysis-runs-status-bulk'),
    path('runs/<int:pk>/status/', AnalysisRunStatusView.as_view(), name='analysis-runs-status'),
    path('runs/<int:pk>/', AnalysisRunDetailView.as_view(), name='analysis-runs-detail'),
]
