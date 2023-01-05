from datetime import datetime, timedelta
import os
import json
from astropy.time import Time
import requests
import time
import copy
import logging

logger = logging.getLogger(__name__)


class AlerceQuery:
 
    def __init__(self, days_ago, ndet):
        self.days_ago = days_ago # Objects discovered within this timeframe
        self.ndet = ndet # At least this many detections
        startdate = Time(datetime.utcnow(), scale='utc').mjd - self.days_ago
        enddate = Time(datetime.utcnow(), scale='utc').mjd
        self.search_url = "https://api.alerce.online/ztf/v1/objects/?class=SN&ndet={}&probability=0.5&firstmjd={}&firstmjd={}&page_size=1000&count=false".format(ndet, startdate, enddate)
        
        self.candidates, self.coords = self.get_candidates(self)
        self.det, self.nondet = self.get_photometry(self)


    def get_candidates(self, *args, **kwargs):

        r = requests.get(self.search_url, headers={'accept': 'application/json'})
        response = json.loads(r.text)

        ztfnames = []
        coords = {}
        try:
            for i in response['items']:
                if not i['stellar']:
                    ztfnames.append(i['oid'])
                    coords[i['oid']] = [i['meanra'], i['meandec']]
        except Exception as e:
            logger.warning('Getting candidates failed, response was {}'.format(e))
            raise(e)

        return ztfnames, coords


    def get_photometry(self, *args, **kwargs):
        phot = {}
        nondets = {}
        for name in self.candidates:
            alerce_url = 'https://api.alerce.online/ztf/v1/objects/{}/lightcurve'.format(name)
            
            g_dets = {}
            r_dets = {}

            g_nondets = {}
            r_nondets = {}

            ### Query Alerce
            lc = requests.get(alerce_url, headers={'accept': 'application/json'})
            try:
                detections = json.loads(lc.text)['detections']
            except:
                #print('No detections for {}'.format(name))
                continue
            
            for det in detections:
                if det['fid'] == 1:
                    g_dets[str(det['mjd'])] = [det['magpsf'], det['sigmapsf']]
                else:
                    r_dets[str(det['mjd'])] = [det['magpsf'], det['sigmapsf']]
            
            try:
                nondetections = json.loads(lc.text)['non_detections']
            except:
                #print('No nondetections for {}'.format(name))
                continue
            
            for nondet in nondetections:
                if nondet['fid'] == 1:
                    g_nondets[str(nondet['mjd'])] = nondet['diffmaglim']
                else:
                    r_nondets[str(nondet['mjd'])] = nondet['diffmaglim']
            
            phot[name] = {'g': g_dets,
                          'r': r_dets
                        }
            nondets[name] = {'g': g_nondets,
                            'r': r_nondets
                        }

        return phot, nondets


class BasicAlerceQuery(AlerceQuery):

    def magnitude_cut(self, mag_lower): 
        for name in copy.copy(self.candidates):
            current_phot = self.det.get(name)
            if not current_phot:
                self.candidates.remove(name)
                continue

            g_mags = [p[0] for p in current_phot['g'].values()]
            r_mags = [p[0] for p in current_phot['r'].values()]

            if not any([g < mag_lower for g in g_mags]) and not any([r < mag_lower for r in r_mags]):
                self.candidates.remove(name)

        return True

    
    def last_nondetection_cut(self, days_since):
        for name in copy.copy(self.candidates):
            current_nondet = self.nondet.get(name)
            if not current_nondet:
                self.candidates.remove(name)
                continue
            
            g_nondets = current_nondet['g'].keys()
            r_nondets = current_nondet['r'].keys()

            if not any([float(g) > Time(datetime.utcnow(), scale='utc').mjd - days_since for g in g_nondets]) and not any([float(r) > Time(datetime.utcnow(), scale='utc').mjd - days_since for r in r_nondets]):
                self.candidates.remove(name)

        return True


    def validate_candidates(self, mag_lower, days_since, *args, **kwargs):
        #print('Starting with candidates {}'.format(self.candidates))
        mag_cut = self.magnitude_cut(mag_lower)
        #print('After magnitude cut, left with {}'.format(self.candidates))
        nondet_cut = self.last_nondetection_cut(days_since)
        #print('After nondetection cut, left with {}'.format(self.candidates))

        return True
