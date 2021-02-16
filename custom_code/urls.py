from django.urls import path

from custom_code.views import TNSTargets, PaperCreateView, PhotSchedulingView, phot_scheduling_view

app_name = 'custom_code'

urlpatterns = [
    path('tnstargets/', TNSTargets.as_view(), name='tns-targets'),
    path('create-paper/', PaperCreateView.as_view(), name='create-paper'),
    #path('scheduling-phot/', PhotSchedulingView.as_view(), name='scheduling-phot')
    path('scheduling-phot/', phot_scheduling_view, name='scheduling-phot'),
]
