"""snex2 URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path

from django.urls import include

from custom_code.views import TargetListView, target_redirect_view#

urlpatterns = [
    path('targets/', TargetListView.as_view(), name='list'),
    path('redirect/', target_redirect_view, name='redirect'),
    path('', include('tom_common.urls')),
    path('snex2/', include('custom_code.urls'))
]
