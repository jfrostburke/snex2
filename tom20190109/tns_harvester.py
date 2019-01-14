from tom_catalogs.harvester import AbstractHarvester

import os
import requests
import json
from collections import OrderedDict

def get(term):
  api_key = os.environ['SNEXBOT_APIKEY']
  url = "https://wis-tns.weizmann.ac.il/api/get"
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

def convert_radec(ra,dec):
    
    [hr,mi,se] = [float(x) for x in ra.split(':')]
    ra_hr = hr + mi/60. + se/3600.
    ra_deg = (ra_hr/24.)*360.
    
    [de,mi,se] = [abs(float(x)) for x in dec.split(':')]
    dec_deg = de + mi/60. + se/3600.
    if '-' in dec: dec_deg = -dec_deg
    
    return ra_deg, dec_deg

class TNSHarvester(AbstractHarvester):
    name = 'TNS'

    def query(self, term):
        self.catalog_data = get(term)

    def to_target(self):
        target = super().to_target()
        target.type = 'SIDEREAL'
        target.identifier = (self.catalog_data['name_prefix'] +
            self.catalog_data['name'])
        target.ra, target.dec = convert_radec(
            self.catalog_data['ra'], self.catalog_data['dec'])
        return target
