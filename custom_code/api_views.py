from django.conf import settings
from django.contrib.auth.models import User, Group
from guardian.shortcuts import assign_perm
from tom_dataproducts.api_views import DataProductViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.mixins import CreateModelMixin
from tom_dataproducts.models import DataProduct, ReducedDatum
from tom_targets.models import Target, TargetName
from custom_code.models import ReducedDatumExtra
from tom_common.hooks import run_hook
from .processors.data_processor import run_custom_data_processor
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
        
        upload_extras = json.loads(request.data['upload_extras'])
        dp_type = request.data['data_product_type']
        
        request.data['data'] = request.FILES['file']
        
        # Add the SNEx2 targetid of the target to request
        targetname = request.data['targetname']
        targetquery = Target.objects.filter(name=targetname)
        if not targetquery:
            targetquery = TargetName.objects.filter(name=targetname)
            targetid = targetquery.first().target_id
        else:
            targetid = targetquery.first().id
        request.data['target'] = targetid

        # Sort the extras keywords into the appropriate dictionaries
        extras = {}
        extras['reduction_type'] = upload_extras.pop('reduction_type', '')
        background_subtracted = upload_extras.pop('background_subtracted', '')
        if background_subtracted:
            extras['background_subtracted'] = background_subtracted
            extras['subtraction_algorithm'] = upload_extras.pop('subtraction_algorithm', '')
            extras['template_source'] = upload_extras.pop('template_source', '')
        
        used_in = upload_extras.pop('used_in', '')
        if used_in:
            if ',' in used_in:
                last_name = used_in.split(',')[0]
                first_name = used_in.split(', ')[1]
                paper_query = Paper.objects.filter(
                    target_id=targetid,
                    author_last_name=last_name,
                    author_first_name=first_name)
                if len(paper_query) != 0:
                    paper_string = str(paper_query.first())
                    upload_extras['used_in'] = paper_string
            else:
                paper_query = Paper.objects.filter(target_id=targetid, author_last_name=used_in)
                if len(paper_query) != 0:
                    paper_string = str(paper_query.first())
                    upload_extras['used_in'] = paper_string

        response = CreateModelMixin.create(self, request, *args, **kwargs)
        if response.status_code == status.HTTP_201_CREATED:
            dp = DataProduct.objects.get(pk=response.data['id'])
            try:
                #run_hook('data_product_post_upload', dp)
                reduced_data = run_custom_data_processor(dp, extras)
                if not settings.TARGET_PERMISSIONS_ONLY:
                    for group_name in settings.DEFAULT_GROUPS:#response.data['group']:
                        group = Group.objects.get(name=group_name)
                        assign_perm('tom_dataproducts.view_dataproduct', group, dp)
                        assign_perm('tom_dataproducts.delete_dataproduct', group, dp)
                        assign_perm('tom_dataproducts.view_reduceddatum', group, reduced_data)
                # Make the ReducedDatumExtra row corresponding to this dp
                upload_extras['data_product_id'] = dp.id
                reduced_datum_extra = ReducedDatumExtra(
                    target_id = targetid,
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
