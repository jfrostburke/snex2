from django.urls import path

from custom_code.views import TNSTargets, PaperCreateView, scheduling_view, ReferenceStatusUpdateView, ObservationGroupDetailView, observation_sequence_cancel_view, approve_or_reject_observation_view, AuthorshipInformation, download_photometry_view

app_name = 'custom_code'

urlpatterns = [
    path('tnstargets/', TNSTargets.as_view(), name='tns-targets'),
    path('create-paper/', PaperCreateView.as_view(), name='create-paper'),
    path('scheduling/', scheduling_view, name='scheduling'),
    path('update-reference-status/', ReferenceStatusUpdateView.as_view(), name='update-reference-status'),
    path('observationgroup/<int:pk>/', ObservationGroupDetailView.as_view(), name='observationgroup-detail'),
    path('observation/cancel/', observation_sequence_cancel_view, name='observation-sequence-cancel'),
    path('observation/approve-or-reject/', approve_or_reject_observation_view, name='approve-or-reject-observation'),
    path('authorshipinformation/', AuthorshipInformation.as_view(), name='authorship'),
    path('download-photometry/<int:targetid>/', download_photometry_view, name='download-photometry'),

]
