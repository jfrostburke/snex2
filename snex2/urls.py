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

from custom_code.views import TargetListView, CustomTargetCreateView, CustomDataProductUploadView, CustomDataProductDeleteView, target_redirect_view, add_tag_view, save_target_tag_view, targetlist_collapse_view, save_dataproduct_groups_view, change_target_known_to_view, change_interest_view, search_name_view, add_target_to_group_view, remove_target_from_group_view, change_observing_priority_view, CustomObservationListView, make_tns_request_view, fit_lightcurve_view, save_lightcurve_params_view, CustomObservationCreateView, query_swift_observations_view, load_lightcurve_view, make_thumbnail_view, InterestingTargetsView, BrokerTargetView, change_broker_target_status_view
from custom_code.api_views import CustomDataProductViewSet
from rest_framework.routers import DefaultRouter
from custom_code.dash_apps import lightcurve, spectra, spectra_individual

custom_router = DefaultRouter()
custom_router.register(r'photometry-upload', CustomDataProductViewSet, 'photometry-upload')


urlpatterns = [
    path('targets/', TargetListView.as_view(), name='list'),
    path('redirect/', target_redirect_view, name='redirect'),
    path('add_tag/', add_tag_view, name='add_tag'),
    path('save_target_tag/', save_target_tag_view, name='save_target_tag'),
    path('targetlist_collapse/', targetlist_collapse_view, name='targetlist_collapse'),
    path('create-target/', CustomTargetCreateView.as_view(), name='create-target'),
    path('custom-data-upload/', CustomDataProductUploadView.as_view(), name='custom-data-upload'),
    path('custom-upload-delete/<int:pk>/', CustomDataProductDeleteView.as_view(), name='custom-upload-delete'),
    path('pipeline-upload/', include(custom_router.urls)),
    path('save_dataproduct_groups/', save_dataproduct_groups_view, name='save_dataproduct_groups'),
    path('change-target-known-to/', change_target_known_to_view, name='change-target-known-to'),
    path('change-interest/', change_interest_view, name='change-interest'),
    path('name-search/', search_name_view, name='name-search'),
    path('add-target-to-group/', add_target_to_group_view, name='add-target-to-group'),
    path('remove-target-from-group/', remove_target_from_group_view, name='remove-target-from-group'),
    path('change-observing-priority/', change_observing_priority_view, name='change-observing-priority'),
    path('make-tns-request/', make_tns_request_view, name='make-tns-request'),
    path('fit-lightcurve/', fit_lightcurve_view, name='fit-lightcurve'),
    path('save-lightcurve-params/', save_lightcurve_params_view, name='save-lightcurve-params'),
    path('scheduling/', CustomObservationListView.as_view(), name='scheduling'),
    path('submit/<str:facility>/', CustomObservationCreateView.as_view(), name='submit-lco-obs'),
    path('query-swift-observations/', query_swift_observations_view, name='query-swift-observations'),
    path('load-lc/', load_lightcurve_view, name='load-lc'),
    path('make-thumbnail/', make_thumbnail_view, name='make-thumbnail'),
    path('interesting-targets/', InterestingTargetsView.as_view(), name='interesting-targets'),
    path('alerts/broker-targets/', BrokerTargetView.as_view(), name='broker-targets'),
    path('change-broker-target-status/', change_broker_target_status_view, name='change-broker-target-status'),
    path('', include('tom_registration.registration_flows.approval_required.urls', namespace='registration')),
    path('', include('tom_common.urls')),
    path('snex2/', include('custom_code.urls')),
    path('django_plotly_dash/', include('django_plotly_dash.urls')),
    #path('__debug__/', include('debug_toolbar.urls')),
]
