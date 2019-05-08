from django.shortcuts import render
from django.views.generic import TemplateView, View

import os
import requests
import json
from datetime import datetime
from datetime import timedelta
from astropy.coordinates import SkyCoord
from astropy import units as u

# Create your views here.
class TNSTargets(TemplateView):

    def day_diff(now, then):
        then = datetime.strptime(then, '%Y-%m-%d %H:%M:%S')
        diff = (now - then).total_seconds() / 86400
        return diff

    template_name = 'custom_code/tns_targets.html'

    api_key = os.environ['SNEXBOT_APIKEY']
    search_url = "https://wis-tns.weizmann.ac.il/api/get/search"
    object_url = "https://wis-tns.weizmann.ac.il/api/get/object"
    tess_url = "https://mast.stsci.edu/tesscut/api/v0.1/sector"

    targets = []
    
    with requests.Session() as s: 
    
        #Get list of recent candidates
        days_ago = 0.3
    
        date = str(datetime.utcnow() - timedelta(days=days_ago))
        json_list = {'public_timestamp': date}
        get_data = [('api_key',(None, api_key)),
    		 ('data',(None,json.dumps(json_list)))]

        obj_list = s.post(search_url, files=get_data)
        obj_list = json.loads(obj_list.text)['data']['reply']
        obj_list = obj_list[-10:]
    
        for obj in obj_list:
            json_list = {'objname': obj['objname'],'photometry':1}
            get_data = [('api_key',(None, api_key)),
            	     ('data',(None,json.dumps(json_list)))]
               
            obj_data = s.post(object_url, files=get_data)
            obj_data = json.loads(obj_data.text)['data']['reply']

            coords = SkyCoord(obj_data['radeg'], obj_data['decdeg'], unit=u.deg)
            
            #Get recent and limiting mags
            recent_jd = max([x['jd'] for x in obj_data['photometry']])

            phot_lnd = {}
            phot_recent = {}

            for observation in obj_data['photometry']:
                if 'Last non detection' in observation['remarks']:
                    phot_lnd = observation #lnd: last non detection
                elif observation['jd'] == recent_jd:
                    phot_recent = observation

            now = datetime.utcnow()

            diff = day_diff(now, phot_recent['obsdate'])
            mag_recent = {
                'mag': float(phot_recent['flux']),
                'filt': phot_recent['filters']['name'],
                'time': float(diff)
            }
            mag_recent = '{mag:.2f} ({filt}: {time:.2f} days ago)'.format(
                mag=mag_recent['mag'],
                filt=mag_recent['filt'],
                time=mag_recent['time'],
            )

            if phot_lnd:            
                diff = day_diff(now, phot_lnd['obsdate'])
                mag_lim = {
                    'mag': float(phot_lnd['limflux']),
                    'filt': phot_lnd['filters']['name'],
                    'time': float(diff)
                }  
                mag_lim = '{mag:.2f} ({filt}: {time:.2f} days ago)'.format(
                    mag=mag_lim['mag'],
                    filt=mag_lim['filt'],
                    time=mag_lim['time'],
                )
            else:
                mag_lim = 'Archival'

            #Check if it's in TESS
            params = {
                'ra': obj_data['radeg'],
                'dec': obj_data['decdeg']
            }
            tess_response = requests.get(tess_url, params=params)
            tess_response = tess_response.json()['results']
            tess_response = sorted([x['sectorName'] for x in tess_response])


            target = {'name': obj['prefix']+obj['objname'],
                'link': 'https://wis-tns.weizmann.ac.il/object/{name}'.format(
                    name=obj['objname']),
                'ra': obj_data['radeg'],
                'dec': obj_data['decdeg'],
                'coords': coords.to_string('hmsdms',sep=':',precision=1,alwayssign=True),
                'tess_response': tess_response,
                'mag_recent': mag_recent,
                'mag_lim': mag_lim
            }
            targets.append(target)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['targets'] = self.targets
        return context
