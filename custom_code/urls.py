from django.urls import path

from custom_code.views import TNSTargets, PaperCreateView, scheduling_view, ReferenceStatusUpdateView

app_name = 'custom_code'

urlpatterns = [
    path('tnstargets/', TNSTargets.as_view(), name='tns-targets'),
    path('create-paper/', PaperCreateView.as_view(), name='create-paper'),
    path('scheduling/', scheduling_view, name='scheduling'),
    path('update-reference-status/', ReferenceStatusUpdateView.as_view(), name='update-reference-status')
]
