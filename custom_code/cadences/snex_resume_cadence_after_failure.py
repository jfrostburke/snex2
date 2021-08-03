import logging

from tom_common.hooks import run_hook
from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from tom_observations.cadences.resume_cadence_after_failure import ResumeCadenceAfterFailureStrategy
from custom_code.hooks import _get_session, _load_table
from django.conf import settings
from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from contextlib import contextmanager
from urllib.parse import urlencode
from dateutil.parser import parse

logger = logging.getLogger(__name__)

class SnexResumeCadenceAfterFailureStrategy(ResumeCadenceAfterFailureStrategy):

    def run(self):

        # gets the most recent observation assuming the observation requests submitted from SNEx1 are being continuously sycned with SNEx2
        last_obs = self.dynamic_cadence.observation_group.observation_records.order_by('-created').first()

        # Make a call to the facility to get the current status of the observation
        facility = get_service_class(last_obs.facility)()
        facility.update_observation_status(last_obs.observation_id)  # Updates the DB record
        last_obs.refresh_from_db()  # Gets the record updates

        # Boilerplate to get necessary properties for future calls
        start_keyword, end_keyword = facility.get_start_end_keywords()
        observation_payload = last_obs.parameters

        # Cadence logic
        # If the observation hasn't finished, do nothing
        if not last_obs.terminal:
            return
        elif last_obs.failed:  # If the observation failed
            # Submit next observation to be taken as soon as possible with the same window length
            window_length = parse(observation_payload[end_keyword]) - parse(observation_payload[start_keyword])
            observation_payload[start_keyword] = datetime.now().isoformat()
            observation_payload[end_keyword] = (parse(observation_payload[start_keyword]) + window_length).isoformat()
        else:  # If the observation succeeded
            # Advance window normally according to cadence parameters
            observation_payload = self.advance_window(
                observation_payload, start_keyword=start_keyword, end_keyword=end_keyword
            )

        observation_payload = self.update_observation_payload(observation_payload)

        # Submission of the new observation to the facility
        obs_type = last_obs.parameters.get('observation_type')
        form = facility.get_form(obs_type)(observation_payload)
        if form.is_valid():
            observation_ids = facility.submit_observation(form.observation_payload())
        else:
            logger.error(msg=f'Unable to submit next cadenced observation: {form.errors}')
            raise Exception(f'Unable to submit next cadenced observation: {form.errors}')

        # Creation of corresponding ObservationRecord objects for the observations
        new_observations = []
        for observation_id in observation_ids:
            # Create Observation record
            record = ObservationRecord.objects.create(
                target=last_obs.target,
                facility=facility.name,
                parameters=observation_payload,
                observation_id=observation_id
            )
            # Add ObservationRecords to the DynamicCadence
            self.dynamic_cadence.observation_group.observation_records.add(record)
            self.dynamic_cadence.observation_group.save()
            new_observations.append(record)

        # Update the status of the ObservationRecords in the DB
        for obsr in new_observations:
            facility = get_service_class(obsr.facility)()
            facility.update_observation_status(obsr.observation_id)

            ### Sync with SNEx1

            # Get the ID of the sequence in the SNEx1 obsrequests table
            try:
                snex_id = int(self.dynamic_cadence.observation_group.name) #requestsid 
            except:
                logger.info('Unable to find SNEx1 ID corresponding to observation group {}'.format(self.dynamic_cadence.observation_group.name))
                snex_id = ''
            # Get the observation details from the submitted parameters
            params = obsr.parameters

            # Get the requestsgroup ID from the LCO API using the observation ID
            obs_id = int(obsr.observation_id)
            LCO_SETTINGS = settings.FACILITIES['LCO']
            PORTAL_URL = LCO_SETTINGS['portal_url']
            portal_headers = {'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}
    
            query_params = urlencode({'request_id': obs_id})
    
            r = requests.get('{}/api/requestgroups?{}'.format(PORTAL_URL, query_params), headers=portal_headers)
            requestgroups = r.json()
            if requestgroups['count'] == 1:
                requestgroup_id = int(requestgroups['results'][0]['id'])

            # Use a hook to sync this observation request with SNEx1
            #run_hook('sync_observation_with_snex1', snex_id, params, requestgroup_id)

        return new_observations 

