import os
from gw.models import GWFollowupGalaxies
from tom_common.hooks import run_hook
from tom_targets.models import Target, TargetExtra
from tom_nonlocalizedevents.models import EventSequence
from custom_code.views import cancel_observation, Snex1ConnectionError
from custom_code.hooks import _return_session
import logging
from django.conf import settings


logger = logging.getLogger(__name__)

def cancel_gw_obs(galaxy_ids=[], sequence_id=None, wrapped_session=None):
    """
    Hook to cancel observations for galaxies corresponding to a GW EventSequence
    Takes as input either a list of GWFollowupGalaxy IDs or an EventSequence ID
    Cancels in SNEx2 and SNEx1
    """

    if not galaxy_ids and not sequence_id:
        logger.warning('Must provide either list of galaxy ids or an EventSequence id to cancel observations')
        return

    if galaxy_ids:
        galaxies = GWFollowupGalaxies.objects.filter(id__in=galaxy_ids)

    elif sequence_id:
        sequence = EventSequence.objects.get(id=sequence_id)
        # Get galaxies associated with this sequence
        galaxies = GWFollowupGalaxy.objects.filter(eventlocalization=sequence.localization)

    targetextras = TargetExtra.objects.filter(key='gwfollowupgalaxy_id', value__in=[g.id for g in galaxies])
    targets = [t.target for t in targetextras]

    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(settings.SNEX1_DB_URL)
    
    for target in targets:
        ### Cancel any observation requests for this target
        templates = ObservationRecord.objects.filter(target=target, observation_id='template')
        for template in templates:
            canceled = cancel_observation(template)
            if not canceled:
                response_data = {'failure': 'Canceling sequence failed'}
                raise Snex1ConnectionError(message='This sequence could not be canceled')
            
            obs_group = template.observationgroup_set.first()
            snex_id = int(obs_group.name)

            run_hook('cancel_sequence_in_snex1', snex_id, userid=67, wrapped_session=db_session)

    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()

    else:
        db_session.flush()
    
    if galaxy_ids:
        logger.info('Finished canceling GW follow-up observations for galaxies {}'.format(galaxy_ids))
    else:
        logger.info('Finished canceling GW follow-up observations for sequence {}'.format(sequence_id))
