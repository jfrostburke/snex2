from django.shortcuts import render
from django.conf import settings
from django.http import HttpResponse
from django.db import transaction
from django.db.models import F
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import Group
from django.views.generic import ListView
from guardian.shortcuts import assign_perm
import json
from datetime import datetime, timedelta
from tom_nonlocalizedevents.models import NonLocalizedEvent, EventSequence, EventLocalization
from gw.models import GWFollowupGalaxy
from gw.forms import GWGalaxyObservationForm
from tom_common.hooks import run_hook
from tom_targets.models import Target, TargetExtra
from tom_observations.facility import get_service_class
from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from custom_code.hooks import _return_session
from custom_code.views import Snex1ConnectionError
import logging

logger = logging.getLogger(__name__)

class GWFollowupGalaxyListView(LoginRequiredMixin, ListView):

    template_name = 'gw/galaxy_list.html'
    paginate_by = 30
    model = GWFollowupGalaxy
    context_object_name = 'galaxies'

    def get_queryset(self):
        sequence = EventSequence.objects.get(id=self.kwargs['id'])
        loc = sequence.localization
        galaxies = GWFollowupGalaxy.objects.filter(eventlocalization=loc)
        galaxies = galaxies.annotate(name=F("id"))
        galaxies = galaxies.order_by('-score')

        return galaxies

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        context['superevent_id'] = EventSequence.objects.get(id=self.kwargs['id']).nonlocalizedevent.event_id
        context['galaxy_count'] = len(self.get_queryset())
        context['obs_form'] = GWGalaxyObservationForm()
        return context


def submit_galaxy_observations_view(request):

    ### Get list of GWFollowupGalaxy ids from the request and create Targets
    galaxy_ids = json.loads(request.GET['galaxy_ids'])['galaxy_ids']
    galaxies = GWFollowupGalaxy.objects.filter(id__in=galaxy_ids)

    try:
        #db_session = _return_session()
        failed_obs = []
        with transaction.atomic():
            for galaxy in galaxies:
                newtarget, created = Target.objects.get_or_create(
                        name=galaxy.catalog_objname,
                        ra=galaxy.ra,
                        dec=galaxy.dec,
                        type='SIDEREAL'
                )

                #run_hook('target_post_save', target=newtarget, created=created, group_names=['GWO4'], wrapped_session=db_session)

                ### Create TargetExtra linking the Target with the GWFollowupGalaxy
                if created:
                    targetextralink = TargetExtra(target=newtarget, key='gwfollowupgalaxy_id', value=galaxy.id)
                    targetextralink.save()

                ### Create and submit the observation requests
                form_data = {'name': newtarget.name,
                             'target_id': newtarget.id,
                             'facility': 'LCO',
                             'observation_type': 'IMAGING'
                }

                observing_parameters = {}
                observing_parameters['ipp_value'] = float(request.GET['ipp_value'])
                observing_parameters['max_airmass'] = 2.0 #TODO: Add form field for this?
                observing_parameters['cadence_strategy'] = 'SnexRetryFailedObservationsStrategy'
                observing_parameters['cadence_frequency'] = 1.0 #TODO: This is from SNEx1, change?
                observing_parameters['reminder'] = 1.0
                observing_parameters['facility'] = 'LCO'
                observing_parameters['name'] = newtarget.name
                observing_parameters['target_id'] = newtarget.id
                observing_parameters['delay_start'] = False
                observing_parameters['instrument_type'] = request.GET['instrument_type']
                observing_parameters['observation_type'] = 'IMAGING'
                observing_parameters['observation_mode'] = request.GET['observation_mode']
                observing_parameters['site'] = 'any'
                observing_parameters['min_lunar_distance'] = 20.0
                observing_parameters['proposal'] = 'KEY2020B-001'

                now = datetime.utcnow()
                observing_parameters['start'] = datetime.strftime(now, '%Y-%m-%dT%H:%M:%S')
                if 'RAPID' in request.GET['observation_mode'] or 'CRITICAL'in request.GET['observation_mode']:
                    observing_parameters['end'] = datetime.strftime(now + timedelta(days=1), '%Y-%m-%dT%H:%M:%S')
                else:
                    observing_parameters['end'] = datetime.strftime(now + timedelta(days=float(request.GET['epochs'])), '%Y-%m-%dT%H:%M:%S') #TODO: Check if this is actually what we want

                cadence = {'cadence_strategy': observing_parameters['cadence_strategy'],
                           'cadence_frequency': observing_parameters['cadence_frequency']
                }

                filters = request.GET['filters'].split(',')
                for f in filters:
                    if f in ['g', 'r', 'i']:
                        f += 'p'
                    elif f == 'z':
                        f += 's'
                    observing_parameters[f] = [float(request.GET['exposure_time']), int(request.GET['exposures_per_epoch']), 1]

                form_data['cadence'] = cadence
                form_data['observing_parameters'] = observing_parameters

                facility = get_service_class('LCO')()
                form = facility.get_form(form_data['observation_type'])(observing_parameters)
                if form.is_valid():
                    observation_errors = facility.validate_observation(form.observation_payload())

                    if observation_errors:
                        logger.error(msg=f'Unable to submit observation for {newtarget.name}: {observation_errors}')
                        failed_obs.append(newtarget.name)
                        continue
                        #response_data = {'failure': 'Unable to submit observation for {}'.format(newtarget.name)}
                        #raise Snex1ConnectionError(message='Observation portal returned errors {}'.format(observation_errors))

                else:
                    logger.error(msg=f'Unable to submit observation for {newtarget.name}: {form.errors}')
                    failed_obs.append(newtarget.name)
                    continue
                    #response_data = {'failure': 'Unable to submit observation'}
                    #raise Snex1ConnectionError(message='Observation portal returned errors {}'.format(form.errors))

                new_observations = []
                # Create Observation record
                record = ObservationRecord.objects.create(
                    target=newtarget,
                    facility=facility.name,
                    parameters=form.serialize_parameters(),
                    observation_id='template'
                )
                # Add the request user
                record.parameters['start_user'] = request.user.first_name
                record.save()
                new_observations.append(record)
        
                if len(new_observations) > 1 or form_data.get('cadence'):
                    observation_group = ObservationGroup.objects.create(name=form_data['name'])
                    observation_group.observation_records.add(*new_observations)
                    assign_perm('tom_observations.view_observationgroup', request.user, observation_group)
                    assign_perm('tom_observations.change_observationgroup', request.user, observation_group)
                    assign_perm('tom_observations.delete_observationgroup', request.user, observation_group)

                    if form_data.get('cadence'):
                        DynamicCadence.objects.create(
                            observation_group=observation_group,
                            cadence_strategy=cadence.get('cadence_strategy'),
                            cadence_parameters={'cadence_frequency': cadence.get('cadence_frequency')},
                            active=True
                        )

                    groups = Group.objects.filter(name='GWO4')
                    for record in new_observations:
                        assign_perm('tom_observations.view_observationrecord', groups, record)
                        assign_perm('tom_observations.change_observationrecord', groups, record)
                        assign_perm('tom_observations.delete_observationrecord', groups, record)

                    ## Add the sequence to SNEx1
                    #snex_id = run_hook(
                    #    'sync_sequence_with_snex1',
                    #    form.serialize_parameters(),
                    #    ['GWO4'],
                    #    userid=request.user.id,
                    #    wrapped_session=db_session
                    #)

                    #if len(new_observations) > 1 or form_data.get('cadence'):
                    #    observation_group.name = str(snex_id)
                    #    observation_group.save()

                    #    for record in new_observations:
                    #        record.parameters['name'] = snex_id
                    #        record.save()

                    ### TODO: Log the target in a new snex1 table?

                ### Submit pointing to TreasureMap

            raise Snex1ConnectionError(message="We got to the end but raise an error to roll back the db")
        if not failed_obs:
            failed_obs_str = 'All observations submitted successfully'
        else:
            failed_obs_str = 'Observations failed to submit for the following galaxies: ' + ','.join(failed_obs)
        response_data = {'success': 'Submitted',
                         'failed_obs': failed_obs_str}
        #db_session.commit()

    except Exception as e:
        logger.error('Creating galaxy Target objects and scheduling observations failed with error: {}'.format(e))
        response_data = {'failure': 'Creating galaxy Target objects and scheduling observations failed'}
        #db_session.rollback()

    finally:
        print('Done')
        #db_session.close()

    return HttpResponse(json.dumps(response_data), content_type='application/json')


def cancel_galaxy_observations_view(request):

    ### Get list of GWFollowupGalaxy ids from the request and create Targets
    try:
        db_session = _return_session()

        galaxy_ids = json.loads(request.GET['galaxy_ids'])
        with transaction.atomic():
            run_hook('cancel_gw_obs', galaxy_ids=galaxy_ids, wrapped_session=db_session)

        response_data = {'success': 'Canceled'}
        db_session.commit()

    except Exception as e:
        logger.error('Canceling follow-up observations failed with error: {}'.format(e))
        response_data = {'failure': 'Could not cancel follow-up observations for these galaxies'}
        db_session.rollback()

    finally:
        db_session.close()

    return HttpResponse(json.dumps(response_data), content_type='application/json')

