from django.urls import path

from custom_code.views import TNSTargets

from custom_code.dash_apps import spectra
from custom_code.dash_apps import simpleexample

app_name = 'custom_code'

urlpatterns = [
    path('tnstargets/', TNSTargets.as_view(), name='tns-targets'),
]
