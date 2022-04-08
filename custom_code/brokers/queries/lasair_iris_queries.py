from lasair import LasairError, lasair_client as lasair
import os
import json
from astropy.time import Time
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class LasairIrisQuery:

    token = os.environ['LASAIR_IRIS_TOKEN']

    def __init__(self, stream_name, ncandidates, days_ago):
        self.stream_name = stream_name
        self.ncandidates = ncandidates
        self.days_ago = days_ago
        
        self.candidates, self.coords, self.redshifts, self.tnsnames, self.classes = self.get_candidates(self)
        self.det, self.nondet = self.get_photometry(self)


    def get_candidates(self, *args, **kwargs):
        L = lasair(self.token)
        results = L.streams(self.stream_name, limit=self.ncandidates)
        startdate = datetime.utcnow() - timedelta(days=self.days_ago)

        ztfnames = []
        coords = {}
        redshifts = {}
        tnsnames = {}
        classes = {}
        for result in results:
            if datetime.strptime(result['UTC'], "%Y-%m-%d %H:%M:%S") < startdate:
                break # Reached the end of the candidates from the last n days
            if result['objectId'] in ztfnames:
                continue # Some candidates are repeated in the query

            try:
                name = result['objectId']
                ztfnames.append(name)
                coords[name] = [float(result['ramean']), float(result['decmean'])]

                if result.get('tns_z'):
                    redshifts[name] = {'z': float(result['tns_z']), 'source': 'TNS'}
                elif result.get('sherlock_z'):
                    redshifts[name] = {'z': float(result['sherlock_z']), 'source': 'Sherlock'}

                if result.get('tns_name'):
                    tnsnames[name] = result['tns_name']

                if result.get('type'):
                    classes[name] = result['type']

            except Exception as e:
                logger.warning('Getting candidates failed, response was {}'.format(e))
            
        return ztfnames, coords, redshifts, tnsnames, classes


    def get_photometry(self, *args, **kwargs):
        phot = {}
        nondets = {}
        L = lasair(self.token)
        for name in self.candidates:
            lc = L.lightcurves([name])
            g_dets = {}
            r_dets = {}

            g_nondets = {}
            r_nondets = {}
            for epoch in lc[0]:
                if epoch['fid'] == 1 and epoch.get('magpsf', ''):
                    g_dets[str(epoch['jd'] - 2400000.5)] = [epoch['magpsf'], epoch['sigmapsf']]
                elif epoch['fid'] == 2 and epoch.get('magpsf', ''):
                    r_dets[str(epoch['jd'] - 2400000.5)] = [epoch['magpsf'], epoch['sigmapsf']]
                elif epoch['fid'] == 1:
                    g_nondets[str(epoch['jd'] - 2400000.5)] = epoch['diffmaglim']
                else:
                    r_nondets[str(epoch['jd'] - 2400000.5)] = epoch['diffmaglim']

            phot[name] = {'g': g_dets,
                          'r': r_dets}

            nondets[name] = {'g': g_nondets,
                             'r': r_nondets}

        return phot, nondets
