from django.conf import settings
from django.contrib.auth.models import User, Group
from guardian.shortcuts import assign_perm
from tom_dataproducts.api_views import DataProductViewSet
from tom_observations.api_views import ObservationRecordViewSet
from rest_framework import status
from rest_framework.response import Response
from rest_framework.mixins import CreateModelMixin
from tom_dataproducts.models import DataProduct, ReducedDatum
from tom_targets.models import Target, TargetName
from custom_code.models import ReducedDatumExtra, Papers
from tom_common.hooks import run_hook
from .processors.data_processor import run_custom_data_processor
import json

from tom_dataproducts.serializers import DataProductSerializer
from django_filters import rest_framework as drf_filters
from tom_dataproducts.filters import DataProductFilter
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import AllowAny

from tom_observations.facility import get_service_class
from tom_observations.cadence import get_cadence_strategy
from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from rest_framework.exceptions import ValidationError
from django.db import transaction
from custom_code.hooks import _return_session
from urllib.parse import urlencode
import requests
from rest_framework.authentication import SessionAuthentication, BasicAuthentication

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
                paper_query = Papers.objects.filter(
                    target_id=targetid,
                    author_last_name=last_name,
                    author_first_name=first_name)
                if len(paper_query) != 0:
                    paper_id = int(paper_query.first().id)
                    upload_extras['used_in'] = paper_id
            else:
                paper_query = Papers.objects.filter(target_id=targetid, author_last_name=used_in)
                if len(paper_query) != 0:
                    paper_id = int(paper_query.first().id)
                    upload_extras['used_in'] = paper_id

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


class CustomObservationRecordViewSet(ObservationRecordViewSet):

    permission_classes = [AllowAny]
    authentication_classes = [SessionAuthentication, BasicAuthentication]


    def create(self, request, *args, **kwargs):
        """
        Endpoint for submitting a new observation with syncing with SNEx1.
        """
        with transaction.atomic():
            db_session = _return_session()
            # Initialize the observation form, validate the form data, and submit to the observatory
            observation_ids = []
            try:
                facility = get_service_class(self.request.data['facility'])()
                observation_form_class = facility.observation_forms[self.request.data['observation_type']]
                target = Target.objects.get(pk=self.request.data['target_id'])
                observing_parameters = json.loads(self.request.data['observing_parameters'])
                print(self.request.data)
            except KeyError as ke:
                raise ValidationError(f'Missing required field {ke}.')
            except Exception as e:
                raise ValidationError(e)

            observing_parameters.update(
                {k: v for k, v in self.request.data.items() if k in ['name', 'target_id', 'facility']}
            )
            observation_form = observation_form_class(observing_parameters)
            if observation_form.is_valid():
                logger.info(
                    f'Submitting observation to {facility} with parameters {observation_form.observation_payload}'
                )
                observation_ids = facility.submit_observation(observation_form.observation_payload())
                logger.info(f'Successfully submitted to {facility}, received observation ids {observation_ids}')
            else:
                logger.warning(f'Unable to submit observation due to errors: {observation_form.errors}')
                raise ValidationError(observation_form.errors)

            # Normally related objects would be created in the serializer--however, because the ObservationRecordSerializer
            # may need to create multiple objects that are related to the same ObservationGroup and DynamicCadence, we are
            # creating the related objects in the ViewSet.
            cadence = self.request.data.get('cadence')
            observation_group = None

            if len(observation_ids) > 1 or cadence:
                # Create the observation group and assign permissions
                observation_group_name = observation_form.cleaned_data.get('name', f'{target.name} at {facility.name}')
                observation_group = ObservationGroup.objects.create(name=observation_group_name)
                assign_perm('tom_observations.view_observationgroup', self.request.user, observation_group)
                assign_perm('tom_observations.change_observationgroup', self.request.user, observation_group)
                assign_perm('tom_observations.delete_observationgroup', self.request.user, observation_group)
                logger.info(f'Created ObservationGroup {observation_group}.')

                cadence_parameters = json.loads(cadence)
                if cadence_parameters is not None:
                    # Cadence strategy is not used for the cadence form
                    cadence_strategy = cadence_parameters.pop('cadence_strategy', None)
                    if cadence_strategy is None:
                        raise ValidationError('cadence_strategy must be included to initiate a DynamicCadence.')
                    else:
                        # Validate the cadence parameters against the cadence strategy that gets passed in
                        cadence_form_class = get_cadence_strategy(cadence_strategy).form
                        cadence_form = cadence_form_class(cadence_parameters)
                        if cadence_form.is_valid():
                            dynamic_cadence = DynamicCadence.objects.create(
                                observation_group=observation_group,
                                cadence_strategy=cadence_strategy,
                                cadence_parameters=cadence_parameters,
                                active=True
                            )
                            logger.info(f'Created DynamicCadence {dynamic_cadence}.')
                        else:
                            observation_group.delete()
                            raise ValidationError(cadence_form.errors)

            # Create the serializer data used to create the observation records
            serializer_data = []
            for obsr_id in observation_ids:
                obsr_data = {  # TODO: at present, submitted fields have to be added to this dict manually, maybe fix?
                    'name': self.request.data.get('name', ''),
                    'target': target.id,
                    'user': self.request.user.id,
                    'facility': facility.name,
                    'groups': json.loads(self.request.data.get('groups', [])),
                    'parameters': observation_form.serialize_parameters(),
                    'observation_id': obsr_id,
                }
                serializer_data.append(obsr_data)

            serializer = self.get_serializer(data=serializer_data, many=True)
            try:
                # Validate the serializer data, create the observation records, and add them to the group, if necessary
                serializer.is_valid(raise_exception=True)
                self.perform_create(serializer)
                if observation_group is not None:
                    observation_group.observation_records.add(*serializer.instance)
            except ValidationError as ve:
                observation_group.delete()
                logger.error(f'Failed to create ObservationRecord due to exception {ve}')
                raise ValidationError(f'''Observation submission successful, but failed to create a corresponding
                                          ObservationRecord due to exception {ve}.''')

            ### Sync new sequences with SNEx1
            # Get the group ids to pass to SNEx1
            group_names = []
            if not settings.TARGET_PERMISSIONS_ONLY:
                for group in json.loads(self.request.data.get('groups', [])):
                    group_names.append(Group.objects.get(pk=group['id']).name)

            ## Run the hook to add the sequence to SNEx1
            snex_id = run_hook(
                    'sync_sequence_with_snex1',
                    observation_form.serialize_parameters(),
                    group_names,
                    userid=int(self.request.data.get('user_id', '3')),
                    wrapped_session=db_session)

            # Change the name of the observation group, if one was created
            if len(observation_ids) > 1 or cadence:
                observation_group.name = str(snex_id)
                observation_group.save()

                for record in observation_group.observation_records.all():
                    record.parameters['name'] = snex_id
                    record.save()

            # Now run the hook to add each observation record to SNEx1
            for record in observation_group.observation_records.all():
                # Get the requestsgroup ID from the LCO API using the observation ID
                obs_id = int(record.observation_id)
                LCO_SETTINGS = settings.FACILITIES['LCO']
                PORTAL_URL = LCO_SETTINGS['portal_url']
                portal_headers = {'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}

                query_params = urlencode({'request_id': obs_id})

                r = requests.get('{}/api/requestgroups?{}'.format(PORTAL_URL, query_params), headers=portal_headers)
                requestgroups = r.json()
                if requestgroups['count'] == 1:
                    requestgroup_id = int(requestgroups['results'][0]['id'])

                run_hook('sync_observation_with_snex1', 
                         snex_id, 
                         record.parameters, 
                         requestgroup_id, 
                         wrapped_session=db_session)

            db_session.commit()

        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
