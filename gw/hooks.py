import os
from gw.models import GWFollowupGalaxies
from tom_common.hooks import run_hook
from tom_targets.models import Target, TargetExtra
from tom_nonlocalizedevents.models import EventSequence
from custom_code.views import cancel_observation, Snex1ConnectionError
from custom_code.hooks import _return_session, _load_table
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


def ingest_gw_galaxy_into_snex1(target_id, event_id, wrapped_session=None):

    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(_snex1_address)

    o4_galaxies = _load_table('o4_galaxies', db_address=_snex1_address)

    existing_target = db_session.query(o4_galaxies).filter(o4_galaxies.targetid==target_id)
    if existing_target.count() > 0:
        if any([t.event_id == event_id for t in existing_target]):
            logger.info('Already ingested target {} into o4_galaxies table for event {}'.format(target_id, event_id))

        else:
            logger.info('Found existing target {} in o4_galaxies table, copying it'.format(target_id))
            existing_target_row = existing_target.first()
            existing_table = existing_target_row.__table__ #Somehow this is different than the o4_galaxies object
            
            non_pk_columns = [k for k in existing_table.columns.keys() if k not in existing_table.primary_key.columns.keys()]
            data = {c: getattr(existing_target_row, c) for c in non_pk_columns}
            data['event_id'] = event_id

            db_session.add(o4_galaxies(**data))

    else:
        snex2_target = Target.objects.get(id=target_id)
        ra0 = snex2_target.ra
        dec0 = snex2_target.dec

        db_session.add(o4_galaxies(targetid=target_id, event_id=event_id, ra0=ra0, dec0=dec0))

    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()

    else:
        db_session.flush()

    logger.info('Finished ingesting target {} into o4_galaxies'.format(target_id))
