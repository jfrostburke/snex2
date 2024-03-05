import os
import requests


TM_TOKEN = os.getenv('TM_TOKEN', '')
TM_POINTING_URL = 'http://treasuremap.space/api/v0/pointings'
INSTRUMENT_DICT = {'2M0-SCICAM-SPECTRAL': 56, '1M0-SCICAM-SINISTRO': 9} #TODO: Check these


def build_tm_pointings(target, observation_parameters):
    
    pointings = []

    planned_pointing = {'instrument_id': INSTRUMENT_DICT[observation_parameters['instrument_type']],
                        'depth': 20.0,
                        'depth_unit': 'ab_mag',
                        'pos_angle': '0.0',
                        'status': 'planned',
                        'ra': str(target.ra),
                        'dec': str(target.dec),
                        'time': observation_parameters['start']
    }

    filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
    for filt in filters:
        if filt in observation_parameters.keys():
            copy_planned_pointing = planned_pointing
            copy_planned_pointing['band'] = filt
            pointings.append(copy_planned_pointing)

    return pointings


def submit_tm_pointings(sequence, pointings):

    tm_planned_report = {'graceid': sequence.nonlocalizedevent.event_id,
                         'api_token': TM_TOKEN,
                         'pointings': pointings
    }

    response = requests.post(TM_POINTING_URL, json=tm_planned_report)
    
    return response.ok


def query_tm_pointings(sequence, status, wl_low=1000, wl_high=20000, wl_unit='angstrom'):

    json_params = {'api_token': TM_TOKEN, 
                   'status': status, 
                   'graceid': squence.nonlocalizedevent.event_id, 
                   'wavelength_regime': str([wl_low, wl_high]), 
                   'wavelength_unit': wl_unit
    }

    response = requests.get(TM_POINTING_URL, json=json_params)

    ### Do something with the response
