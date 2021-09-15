import logging

from tom_common.hooks import run_hook
from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from tom_observations.cadences.retry_failed_observations import RetryFailedObservationsStrategy
from django.conf import settings
from urllib.parse import urlencode
from dateutil.parser import parse

logger = logging.getLogger(__name__)


class SnexRetryFailedObservationsStrategy(RetryFailedObservationsStrategy):

    def run(self):
        failed_observations = [obsr for obsr
                               in self.dynamic_cadence.observation_group.observation_records.all()
                               if obsr.failed]
        new_observations = []
        for obs in failed_observations:
            observation_payload = obs.parameters
            facility = get_service_class(obs.facility)()
            start_keyword, end_keyword = facility.get_start_end_keywords()
            observation_payload = self.advance_window(
                observation_payload, start_keyword=start_keyword, end_keyword=end_keyword
            )
            obs_type = obs.parameters.get('observation_type', None)
            form = facility.get_form(obs_type)(observation_payload)
            form.is_valid()
            observation_ids = facility.submit_observation(form.observation_payload())

            for observation_id in observation_ids:
                # Create Observation record
                record = ObservationRecord.objects.create(
                    target=obs.target,
                    facility=facility.name,
                    parameters=observation_payload,
                    observation_id=observation_id
                )
                self.dynamic_cadence.observation_group.observation_records.add(record)
                self.dynamic_cadence.observation_group.save()
                new_observations.append(record)

        for obsr in new_observations:
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
            run_hook('sync_observation_with_snex1', snex_id, params, requestgroup_id)


        return new_observations
