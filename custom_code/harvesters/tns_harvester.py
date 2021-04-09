from tom_catalogs.harvester import AbstractHarvester

import os
import requests
import json
from collections import OrderedDict

def get(term):
  api_key = os.environ['SNEXBOT_APIKEY']
  url = "https://www.wis-tns.org/api/get"
  try:
    get_url = url + '/object'
    
    # change term to json format
    json_list = [("objname",term)]
    json_file = OrderedDict(json_list)
    
    # construct the list of (key,value) pairs
    get_data = [('api_key',(None, api_key)),
                 ('data',(None,json.dumps(json_file)))]
   
    response = requests.post(get_url, files=get_data)
    response = json.loads(response.text)['data']['reply']
    return response
  except Exception as e:
    return [None,'Error message : \n'+str(e)]

class TNSHarvester(AbstractHarvester):
    name = 'TNS'

    def query(self, term):
        self.catalog_data = get(term)

    def to_target(self):
        target = super().to_target()
        target.type = 'SIDEREAL'
        target.ra = self.catalog_data['radeg']
        target.dec = self.catalog_data['decdeg']
        target.epoch = 2000
        target.identifier = (self.catalog_data['name_prefix'] +
            self.catalog_data['objname'])
        target.name = target.identifier
        extra_names = self.catalog_data['internal_names'].split(',')
        extra_names = list(filter(None, extra_names))
        extra_names = [x.replace(' ','') for x in extra_names]
        target.extra_names = extra_names
        return target
