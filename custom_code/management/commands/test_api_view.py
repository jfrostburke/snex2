from django.core.management.base import BaseCommand
from django.test import Client
from django.contrib.auth.models import User, Group
import os
import json
from django.conf import settings
from datetime import datetime, timedelta
import random
from tom_targets.models import Target

class Command(BaseCommand):

    def add_arguments(self, parser):
        parser.add_argument('--filename', help='Path to the file with observing parameters')
    
    def handle(self, *args, **options):

        filepath = options['filename']
        
        ### Login to client
        c = Client()
        success = c.login(username=os.environ['SNEX2_USER'], password=os.environ['SNEX2_DB_PASSWORD'])
        
        ### Get the static parameters
        group_query = Group.objects.filter(name__in=settings.DEFAULT_GROUPS)
        groups = json.dumps([{'name': g.name, 'id': g.id} for g in group_query])

        me = User.objects.get(id=3)
        cadence = json.dumps({'cadence_strategy': 'SnexResumeCadenceAfterFailureStrategy', 'cadence_frequency': 7.0})
        with open(filepath) as json_file:
            obs_to_schedule = json.load(json_file) 
        
        ### Fill in the rest dynamically
        for target_id, filt_dict in obs_to_schedule.items():
            targetname = Target.objects.get(id=target_id).name
            start = datetime.utcnow() + timedelta(days=random.randint(0, 6))
            end = start + timedelta(days=1)

            start = datetime.strftime(start, '%Y-%m-%dT%H:%M:%S')
            end = datetime.strftime(end, '%Y-%m-%dT%H:%M:%S')
            
            observing_parameters = {'cadence_strategy': 'SnexResumeCadenceAfterFailureStrategy', 
                                    'ipp_value': 0.95, 'max_airmass': 2.0, 'facility': 'LCO', 
                                    'observation_type': 'IMAGING', 'min_lunar_distance': 20, 
                                    'observation_mode': 'NORMAL', 'cadence_frequency': 3.0, 
                                    'proposal': 'KEY2020B-002', 
                                    'instrument_type': '1M0-SCICAM-SINISTRO',
                                    'start': start, 'end': end, 'reminder': 14.0}

            ### Finally, the observations to schedule
        
            #Append filts and exposures
            for filt, exptime in filt_dict.items():
                observing_parameters[filt] = [exptime+0.0, 2, 1]
            
            observing_parameters = json.dumps(observing_parameters)
            try:
                r = c.post('/pipeline-upload/submit-observation/', {'name': targetname, 'observation_type': 'IMAGING', 'cadence': cadence, 'groups': groups, 'observing_parameters': observing_parameters, 'user': me, 'facility': 'LCO', 'target_id': target_id, 'user_id': me.id}, secure=True, follow=True)

                print(r.status_code)
                print(r.data)

            except Exception as e:
                print('Failed submitting request for {} with error {}'.format(targetname, e))
                continue
