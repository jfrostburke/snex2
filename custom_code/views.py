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
    template_name = 'custom_code/tns_targets.html'

    api_key = os.environ['SNEXBOT_APIKEY']
    search_url = "https://wis-tns.weizmann.ac.il/api/get/search"
    object_url = "https://wis-tns.weizmann.ac.il/api/get/object"
    tess_url = "https://mast.stsci.edu/tesscut/api/v0.1/sector"

    targets = []
    
    with requests.Session() as s: 
    
        #Get list of recent candidates
        days_ago = 0.25
    
        date = str(datetime.utcnow() - timedelta(days=days_ago))
        json_list = {'public_timestamp': date}
        get_data = [('api_key',(None, api_key)),
    		 ('data',(None,json.dumps(json_list)))]

        obj_list = s.post(search_url, files=get_data)
        obj_list = json.loads(obj_list.text)['data']['reply']
    
        for obj in obj_list:
            json_list = {'objname': obj['objname']}
            get_data = [('api_key',(None, api_key)),
            	     ('data',(None,json.dumps(json_list)))]
               
            obj_data = s.post(object_url, files=get_data)
            obj_data = json.loads(obj_data.text)['data']['reply']

            coords = SkyCoord(obj_data['radeg'], obj_data['decdeg'], unit=u.deg)

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
                'tess_response': tess_response
            }
            targets.append(target)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['targets'] = self.targets
        return context
