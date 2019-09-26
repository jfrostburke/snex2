import os
import requests
from datetime import datetime
from astropy import units as u
from astropy.coordinates import SkyCoord
from django.conf import settings
from django import forms
from dateutil.parser import parse
from crispy_forms.layout import Layout, Div, HTML
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText, InlineRadios

from tom_observations.facility import GenericObservationForm
from tom_observations.facility import GenericObservationFacility
from tom_targets.models import Target

from tom_observations.facilities import gemini

import logging

logger = logging.getLogger(__name__)

try:
    SNEX_GEMINI_SETTINGS = settings.FACILITIES['SNExGemini']
except KeyError:
    SNEX_GEMINI_SETTINGS = gemini.GEMINI_DEFAULT_SETTINGS

PORTAL_URL = SNEX_GEMINI_SETTINGS['portal_url']
TERMINAL_OBSERVING_STATES = gemini.TERMINAL_OBSERVING_STATES
SITES = gemini.SITES


def proposal_choices():
    return [(proposal, proposal) for proposal in SNEX_GEMINI_SETTINGS['programs']]


def get_site_code_from_program(program_id):
    return program_id.split('-')[0]


class SNExGeminiObservationForm(GenericObservationForm):

    window_size = forms.FloatField(label='', initial=1.0, min_value=0.0)
    max_airmass = forms.FloatField(min_value=1.0, max_value=5.0, initial=1.6, label='')

    ##Optical imaging
    optical_phot_exptime_choices = (
        (0, 0.0),
        (100, 100.0),
        (200, 200.0),
        (300, 300.0),
        (450, 450.0),
        (600, 600.0),
        (900, 900.0),
    )
 
    g_exptime = forms.ChoiceField(choices=optical_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    r_exptime = forms.ChoiceField(choices=optical_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    i_exptime = forms.ChoiceField(choices=optical_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    z_exptime = forms.ChoiceField(choices=optical_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
   
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            self.common_layout,
            Div(
              Div(
                Div(
                    Div(HTML("<p></p>"),
                        PrependedAppendedText(
                            'window_size', 'Once in the next', 'days'
                        ),
                        PrependedText(
                            'max_airmass', 'Airmass <'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">Filter</p>'),css_class='col-md-2'),
                          Div(HTML('<p style="text-align:center;">Exposure time (s)</p>'),css_class='col-md-10'), css_class='form-row',
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">g</p>'),css_class='col-md-2'),
                          Div('g_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">r</p>'),css_class='col-md-2'),
                          Div('r_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">i</p>'),css_class='col-md-2'),
                          Div('i_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">z</p>'),css_class='col-md-2'),
                          Div('z_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                    ), css_class='col-md-8'
                ), css_class='row justify-content-md-center'
              )
            )
        )

    def is_valid(self):
        super().is_valid()
        errors = GeminiFacility.validate_observation(self.observation_payload())
        if errors:
            self.add_error(None, errors)
        return not errors

    def _init_observation_payload(self, target):

        wait = True #On Hold
        coords = SkyCoord(ra=target.ra*u.degree, dec=target.dec*u.degree)
        now = datetime.utcnow()
        sn_name = target.name

        payload = {
            'ready': str(not wait).lower(),
            'prog': os.environ['GEMINI_PROGRAMID'],
            'email': os.environ['GEMINI_EMAIL'],
            'password': os.environ['GEMINI_PASSWORD'],
            'group': '{name} optical imaging'.format(name=target.name),
            'ra': coords.ra.to_string(unit=u.hour,sep=':'),
            'dec': coords.dec.to_string(unit=u.degree,sep=':'),
            'mags': '18.0/g/AB',
            'windowDate': now.strftime('%Y-%m-%d'),
            'windowTime': now.strftime('%H:%M:%S'),
            'windowDuration': int(float(self.data['window_size'])*24), 
            'elevationType': 'airmass',
            'elevationMin': 1.0,
            'elevationMax': str(self.data['max_airmass']).strip(),
            'note': 'No finder chart at the moment, sorry',
            'posangle': 90.
        }  

        return payload

    def observation_payload(self):
        
        target = Target.objects.get(pk=self.data['target_id'])

        obsid_map = {
            'g': '56',
            'r': '57',
            'i': '58',
            'z': '59'
        }

        payloads = {}

        for f in ['g', 'r', 'i', 'z']:
            if float(self.data[f + '_exptime']) > 0.0:
                payloads[f] = self._init_observation_payload(target)
                payloads[f]['obsnum'] = obsid_map[f]
                payloads[f]['target'] = '{name} GMOS {f}'.format(
                    name=target.name, f=f)
                payloads[f]['exptime'] = self.data[f + '_exptime']

        #Need group in there when I'm doing it for real
        #Not sure what to do about mags for now

        return payloads


class GeminiFacility(GenericObservationFacility):
    name = 'Gemini'
    form = SNExGeminiObservationForm
    observation_types = [('IMAGING', 'Optical Imaging')]

    def get_form(self, observation_type):
        return self.form

    @classmethod
    def submit_observation(clz, observation_payloads):

        server = os.environ['GEMINI_SERVER']
        url = server + '/too'

        new_observation_ids = []

        for payload in observation_payloads:
            params = observation_payloads[payload]
            response = requests.post(url, verify=False, params=params)
            print(response.url)
            try:
                response.raise_for_status()
                newobsid = response.text
                new_observation_ids.append(newobsid)
                print(newobsid + ' created and set On Hold')
            except requests.exceptions.HTTPError as exc:
                print('Request failed: ' + response.content)
                raise exc
        
        return new_observation_ids

    @classmethod
    def validate_observation(clz, observation_payload):
        return {}

    @classmethod
    def get_observation_url(clz, observation_id):
        return ''

    @classmethod
    def get_terminal_observing_states(clz):
        return TERMINAL_OBSERVING_STATES

    @classmethod
    def get_observing_sites(clz):
        return SITES

    @classmethod
    def get_observation_status(clz, observation_id):
        return ['IN_PROGRESS']

    @classmethod
    def data_products(clz, observation_record, product_id=None):
        return []
