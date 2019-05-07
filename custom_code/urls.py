from django.urls import path

from custom_code.views import TNSTargets

app_name = 'custom_code'

urlpatterns = [
    path('tnstargets/', TNSTargets.as_view(), name='tns-targets')
]
