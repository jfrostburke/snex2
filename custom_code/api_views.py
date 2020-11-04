from django.conf import settings
from django.contrib.auth.models import User, Group
from guardian.shortcuts import assign_perm
from tom_dataproducts.api_views import DataProductViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.mixins import CreateModelMixin
from tom_dataproducts.models import DataProduct, ReducedDatum
from custom_code.models import ReducedDatumExtra
from tom_common.hooks import run_hook
from .processors.data_processor import run_custom_data_processor, run_pipeline_data_processor
import json

from tom_dataproducts.serializers import DataProductSerializer
from django_filters import rest_framework as drf_filters
from tom_dataproducts.filters import DataProductFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny

import logging
logger = logging.getLogger(__name__)

class CustomDataProductViewSet(DataProductViewSet):

    queryset = DataProduct.objects.all()
    serializer_class = DataProductSerializer
    filter_backends = (drf_filters.DjangoFilterBackend,)
    filterset_class = DataProductFilter
    #permission_required = 'tom_dataproducts.view_dataproduct'
    permission_classes = [AllowAny]
    parser_classes = [MultiPartParser]

    def create(self, request, *args, **kwargs):
        # Test if the username exists
        username = request.data['username']
        if not User.objects.filter(username=username).exists():
            return Response({'User does not exist'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        # Send the upload extras dictionary as json in the request, like:
        upload_extras = json.loads(request.data['upload_extras'])
        dp_type = request.data['data_product_type']
        
        request.data['data'] = request.FILES['file']
        
        # Add default list of groups to request
        default_group_names = ['ANU', 'ARIES', 'CSP', 'CU Boulder', 'e/PESSTO', 'ex-LCOGT', 
                'KMTNet', 'LBNL', 'LCOGT', 'LSQ', 'NAOC', 'Padova', 'QUB', 'SAAO', 'SIRAH', 
                'Skymapper', 'Tel Aviv U', 'U Penn', 'UC Berkeley', 'US GSP', 'UT Austin']
        default_group_ids = []
        for g in default_group_names:
            default_group_ids.append(Group.objects.get(name=g).id)
        request.data['group'] = default_group_ids

        # Sort the extras keywords into the appropriate dictionaries
        extras = {}
        extras['reduction_type'] = upload_extras.pop('reduction_type', '')
        background_subtracted = upload_extras.pop('background_subtracted', '')
        if background_subtracted:
            extras['background_subtracted'] = background_subtracted
            extras['subtraction_algorithm'] = upload_extras.pop('subtraction_algorithm', '')
            extras['template_source'] = upload_extras.pop('template_source', '')
        response = CreateModelMixin.create(self, request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            dp = DataProduct.objects.get(pk=response.data['id'])
            try:
                #run_hook('data_product_post_upload', dp)
                reduced_data = run_pipeline_data_processor(dp, extras)
                if not settings.TARGET_PERMISSIONS_ONLY:
                    for group in response.data['group']:
                        assign_perm('tom_dataproducts.view_dataproduct', group, dp)
                        assign_perm('tom_dataproducts.delete_dataproduct', group, dp)
                        assign_perm('tom_dataproducts.view_reduceddatum', group, reduced_data)
                # Make the ReducedDatumExtra row corresponding to this dp
                upload_extras['data_product_id'] = dp.id
                reduced_datum_extra = ReducedDatumExtra(
                    data_type = dp_type,
                    key = 'upload_extras',
                    value = json.dumps(upload_extras)
                )
                reduced_datum_extra.save()
            except Exception:
                ReducedDatum.objects.filter(data_product=dp).delete()
                dp.delete()
                return Response({'Data processing error': '''There was an error in processing your DataProduct into \
                                                             individual ReducedDatum objects.'''},
                                status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return response
