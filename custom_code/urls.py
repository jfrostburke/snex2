from django.urls import path

from custom_code.views import TNSTargets, PaperCreateView, scheduling_view

app_name = 'custom_code'

urlpatterns = [
    path('tnstargets/', TNSTargets.as_view(), name='tns-targets'),
    path('create-paper/', PaperCreateView.as_view(), name='create-paper'),
    path('scheduling/', scheduling_view, name='scheduling'),
]
