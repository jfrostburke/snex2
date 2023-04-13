from django.core.management.base import BaseCommand
import requests
import os
import logging
from datetime import datetime
from custom_code.models import TimeUsed


logger = logging.getLogger(__name__)


class Command(BaseCommand):

    help = 'Updates the 1m and 2m time used per semester'

    def handle(self, *args, **kwargs):

        ### Get the current semester and the time left in the semester

        semesters = {'2022A': {'start': '2022-02-01 00:00:00', 'end': '2022-07-31 23:59:59'},
                     '2022B': {'start': '2022-08-01 00:00:00', 'end': '2023-01-31 23:59:59'},
                     '2023A': {'start': '2023-02-01 00:00:00', 'end': '2023-07-31 23:59:59'},
                     '2023B': {'start': '2023-08-01 00:00:00', 'end': '2024-01-31 23:59:59'},
                     '2024A': {'start': '2024-02-01 00:00:00', 'end': '2024-07-31 23:59:59'},
                     '2024B': {'start': '2024-08-01 00:00:00', 'end': '2025-01-31 23:59:59'}
        }

        currentdate = datetime.utcnow()

        for semname in semesters:
            semesterstart = datetime.strptime(semesters[semname]['start'], '%Y-%m-%d %H:%M:%S')
            semesterend = datetime.strptime(semesters[semname]['end'], '%Y-%m-%d %H:%M:%S')
            if semesterstart <= currentdate and semesterend >= currentdate:

                break

        totallength = semesterend - semesterstart
        completedlength = currentdate - semesterstart
        completedfrac = completedlength.total_seconds() / totallength.total_seconds()

        ### Get the active Key Project proposal and query the observation portal for time used

        token = os.environ['LCO_APIKEY']

        proposals = requests.get('https://observe.lco.global/api/proposals?active=True&limit=50/',
                                 headers={'Authorization': 'Token ' + token}).json()
        for prop in proposals['results']:
            if 'Global Supernova Project' in prop['title'] and 'KEY' in prop['id']:
                active_prop = prop['id']
                break

        
        timeused = requests.get('https://observe.lco.global/api/proposals/'+active_prop+'/',
                                headers={'Authorization': 'Token '+ token}).json()

        ### Get the amount of time used for per telescope class

        timeaccounting = {'1M0': {}, '2M0': {}}

        for telescope in list(timeaccounting.keys()):
            for tu in timeused['timeallocation_set']:
                if tu['instrument_type'].split('-')[0] == telescope and tu['semester'] == semname:
                    if 'std_time_used' not in timeaccounting[telescope]:
                        timeaccounting[telescope]['std_time_used'] = tu['std_time_used']
                        timeaccounting[telescope]['std_time_allocated'] = tu['std_allocation']
                        timeaccounting[telescope]['tc_time_used'] = tu['tc_time_used']
                        timeaccounting[telescope]['tc_time_allocated'] = tu['tc_allocation']
                        timeaccounting[telescope]['rr_time_used'] = tu['rr_time_used']
                        timeaccounting[telescope]['rr_time_allocated'] = tu['rr_allocation']
                    else:
                        timeaccounting[telescope]['std_time_used'] += tu['std_time_used']
                        timeaccounting[telescope]['std_time_allocated'] += tu['std_allocation']
                        timeaccounting[telescope]['tc_time_used'] += tu['tc_time_used']
                        timeaccounting[telescope]['tc_time_allocated'] += tu['tc_allocation']
                        timeaccounting[telescope]['rr_time_used'] += tu['rr_time_used']
                        timeaccounting[telescope]['rr_time_allocated'] += tu['rr_allocation']

        ### Update the database with current values
        for telescope in list(timeaccounting.keys()):

            tu, created = TimeUsed.objects.get_or_create(
                semester_name=semname, telescope_class=telescope
            )

            tu.__dict__.update(timeaccounting[telescope])
            tu.frac_of_semester = completedfrac

            tu.save()

        logger.info('Successfully updated time used for the semester')
