import logging
import os
import traceback
from astropy.table import Table
from astropy.io import fits
from dateutil.parser import parse
from ligo.skymap import distance

from tom_nonlocalizedevents.alertstream_handlers.gcn_event_handler import extract_all_fields, EXPECTED_FIELDS, get_moc_url_from_skymap_fits_url, handle_retraction
from tom_nonlocalizedevents.alertstream_handlers.igwn_event_handler import handle_igwn_message
from tom_nonlocalizedevents.models import NonLocalizedEvent, EventSequence, EventLocalization
from gw.find_galaxies import generate_galaxy_list
from tom_common.hooks import run_hook

logger = logging.getLogger(__name__)


def handle_igwn_message_with_galaxies(message, metadata):

    ### First, check if the message contains a retraction
    ### and handle that case differently
    alert = message.content[0]
    if alert.get('alert_type', '') == 'RETRACTION':
        NonLocalizedEvent.objects.update_or_create(
            event_id=alert['superevent_id'],
            event_type=NonLocalizedEvent.NonLocalizedEventType.GRAVITATIONAL_WAVE,
            defaults={'state': NonLocalizedEvent.NonLocalizedEventState.RETRACTED}
        )
        
        retracted_event = NonLocalizedEvent.objects.get(event_id=alert['superevent_id'])
        sequences = retracted_event.sequences.all()
        for sequence in sequences:
            run_hook('cancel_gw_obs', galaxy_ids=[], sequence_id=sequence.id)        

        return

    nonlocalizedevent, event_sequence = handle_igwn_message(message, metadata)

    localization = event_sequence.localization
    try:
        generate_galaxy_list(localization)
    except Exception as e:
        logger.error('Could not generate galaxy list with exception {}'.format(e))
        logger.error(traceback.format_exc())


def handle_message(message):
    # It receives a bytestring message or a Kafka message in the LIGO GW format
    # fields must be extracted from the message text and stored into in the model
    if not isinstance(message, bytes):
        bytes_message = message.value()
    else:
        bytes_message = message
    fields = extract_all_fields(bytes_message.decode('utf-8'))
    if fields:
        nonlocalizedevent, nle_created = NonLocalizedEvent.objects.get_or_create(
            event_id=fields['TRIGGER_NUM'],
            event_type=NonLocalizedEvent.NonLocalizedEventType.GRAVITATIONAL_WAVE,
        )
        if nle_created:
            logger.info(f"Ingested a new GW event with id {fields['TRIGGER_NUM']} from alertstream")
        # Next attempt to ingest and build the localization of the event
        multiorder_fits_url = get_moc_url_from_skymap_fits_url(fields['SKYMAP_FITS_URL'])
        header = fits.getheader(multiorder_fits_url, 1)
        creation_date = parse(header.get('DATE'))
        try:
            localization = EventLocalization.objects.get(nonlocalizedevent=nonlocalizedevent, date=creation_date)

        #except EventLocalization.DoesNotExist:
        except:
            distance_mean = header.get('DISTMEAN')
            distance_std = header.get('DISTSTD')
            data = Table.read(multiorder_fits_url)
            row_dist_mean, row_dist_std, _ = distance.parameters_to_moments(data['DISTMU'], data['DISTSIGMA'])
            localization = EventLocalization.objects.create(
                nonlocalizedevent=nonlocalizedevent,
                distance_mean=distance_mean,
                distance_std=distance_std,
                skymap_moc_file_url=multiorder_fits_url,
                date=creation_date
            )
            ### Skipping SkymapTile creation for now TODO: Add it!

            #localization = create_localization_for_multiorder_fits(
            #    nonlocalizedevent=nonlocalizedevent,
            #    multiorder_fits_url=get_moc_url_from_skymap_fits_url(fields['SKYMAP_FITS_URL'])
            #)
        #except Exception as e:
        #    localization = None
        #    logger.error(f'Could not create EventLocalization for messsage: {fields}. Exception: {e}')
        #    logger.error(traceback.format_exc())

        ### Ingest galaxies for this localization into the database
        try:
            generate_galaxy_list(localization)
        except Exception as e:
            logger.error('Could not generate galaxy list with exception {}'.format(e))
            logger.error(traceback.format_exc())

        # Now ingest the sequence for that event
        event_sequence, es_created = EventSequence.objects.update_or_create(
            nonlocalizedevent=nonlocalizedevent,
            localization=localization,
            sequence_id=fields['SEQUENCE_NUM'],
            defaults={
                'event_subtype': fields['NOTICE_TYPE']
            }
        )
        if es_created and localization is None:
            warning_msg = (f'{"Creating" if es_created else "Updating"} EventSequence without EventLocalization:'
                           f'{event_sequence} for NonLocalizedEvent: {nonlocalizedevent}')
            logger.warning(warning_msg)


def handle_retraction_with_galaxies(message):

    retraction = handle_retraction(message)
    
    if not isinstance(message, bytes):
        bytes_message = message.value()
    else:
        bytes_message = message
    fields = extract_all_fields(bytes_message.decode('utf-8'))

    try:
        retracted_event = NonLocalizedEvent.objects.get(event_id=fields['TRIGGER_NUM'])
    except NonLocalizedEvent.DoesNotExist:
        logger.warning((f"Got a Retraction notice for event id {fields['TRIGGER_NUM']}"
                        f"which does not exist in the database"))
        return

    ### Get the ids of the sequences associated with this event and cancel the galaxy observations
    sequences = retracted_event.sequences.all()
    for sequence in sequences:
        run_hook('cancel_gw_obs', galaxy_ids=[], sequence_id=sequence.id)

