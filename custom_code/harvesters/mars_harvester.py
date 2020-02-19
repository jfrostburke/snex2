from tom_catalogs.harvester import AbstractHarvester

import requests
import numpy as np
from astropy.time import Time, TimezoneInfo
import json
from tom_dataproducts.models import ReducedDatum

def get(objectId):
  url = 'https://mars.lco.global/'
  request = {'queries':
    [
      {'objectId': objectId}
    ]
    }

  try:
    r = requests.post(url, json=request)
    results = r.json()['results'][0]['results']
    return results
  
  except Exception as e:
    return [None,'Error message : \n'+str(e)]

class MARSHarvester(AbstractHarvester):
    name = 'MARS'

    def query(self, term):
        self.catalog_data = get(term)

    def to_target(self):
        target = super().to_target()
        target.type = 'SIDEREAL'
        target.epoch = 2000
        
        objectId = [x['objectId'] for x in self.catalog_data][0]
        target.identifier = objectId
        target.name = objectId

        #Each alert has a slight different ra/dec, average them
        candidates = [x['candidate'] for x in self.catalog_data]
        target.ra = np.mean([x['ra'] for x in candidates])
        target.dec = np.mean([x['dec'] for x in candidates])

        return target
