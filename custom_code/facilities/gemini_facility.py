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

from tom_observations.facility import BaseObservationForm
from tom_observations.facility import BaseRoboticObservationFacility
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


class OpticalImagingForm(BaseObservationForm):

    window_size = forms.FloatField(initial=1.0, min_value=0.0, label='')
    max_airmass = forms.FloatField(min_value=1.0, max_value=5.0, initial=1.6, label='')

    # Optical imaging
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
            ),
            self.button_layout()
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
            'prog': os.getenv('GEMINI_PROGRAMID',''),
            'email': os.getenv('GEMINI_EMAIL',''),
            'password': os.getenv('GEMINI_PASSWORD',''),
            'group': 'API Test Optical Imaging',
            'ra': coords.ra.to_string(unit=u.hour,sep=':'),
            'dec': coords.dec.to_string(unit=u.degree,sep=':'),
            'mags': '18.0/g/AB',
            'windowDate': now.strftime('%Y-%m-%d'),
            'windowTime': now.strftime('%H:%M:%S'),
            'windowDuration': int(float(self.data['window_size'])*24),
            'elevationType': 'airmass',
            'elevationMin': 1.0,
            'elevationMax': str(self.data['max_airmass']).strip(),
            'note': 'API Test',
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
                payloads[f]['target'] = 'API Test'
                payloads[f]['exptime'] = self.data[f + '_exptime']

        #Need group in there when I'm doing it for real
        #Not sure what to do about mags for now

        return payloads


class OpticalSpectraForm(BaseObservationForm):

    north_south_choice = (
        ('north', 'North'),
        ('south', 'South'),
    )
    n_or_s = forms.ChoiceField(choices=north_south_choice, initial='north', widget=forms.Select(), required=True,
                             label='')

    window_size = forms.FloatField(initial=1.0, min_value=0.0, label='')
    max_airmass = forms.FloatField(min_value=1.0, max_value=5.0, initial=1.6, label='')

    optical_spec_exptime_choices = (
        (0, 0.0),
        (1200, 1200.0),
        (1500, 1500.0),
        (1700, 1700.0),
    )

    optical_spec_slit_choices = (
        (1, '1.0"'),
        (1.5, '1.5"'),
    )

    slit = forms.ChoiceField(choices=optical_spec_slit_choices, initial=1, widget=forms.Select(), required=True,
                                  label='')
    
    ready_choices = (
        ('true', 'Prepared'),
        ('false', 'On Hold'),
    )
    ready = forms.ChoiceField(choices=ready_choices, initial='false', 
                              widget=forms.Select(), required=True,
                              label='')

    b_exptime = forms.FloatField(initial=0.0, min_value=0.0, 
            required=True, label='')
    r_exptime = forms.FloatField(initial=0.0, min_value=0.0, 
            required=True, label='')

    filter_choices = (
        ('U','U'),
        ('B','B'),
        ('g','g'),
        ('V','V'),
        ('r','r'),
        ('i','i'),
    )

    mag_approx = forms.FloatField(initial=19.0, min_value=0.0, label='')
    mag_approx_filter = forms.ChoiceField(choices=filter_choices, initial='g', widget=forms.Select(), required=True,
                                    label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            self.common_layout,
            Div(
                Div(
                    Div(HTML("<p></p>"),
                        Div(
                            Div(HTML('<p style="text-align:center;">Gemini North or South?</p>'), css_class='col-md-4'),
                            Div('n_or_s', css_class='col-md-8'),
                            css_class='form-row',
                        ),
                        PrependedAppendedText(
                            'window_size', 'Once in the next', 'days'
                        ),
                        PrependedText(
                            'max_airmass', 'Airmass <'
                        ),
                        Div(
                            Div(PrependedText('mag_approx', 'Approximate mag: '),css_class='col-md-8'),
                            Div(HTML('<p style="text-align:center;">Filter:</p>'),css_class='col-md-2'),
                            Div('mag_approx_filter', css_class='col-md-2'),
                            css_class='form-row'
                        ),
                        Div(
                            Div(HTML('<p style="text-align:center;">Grating</p>'), css_class='col-md-2'),
                            Div(HTML('<p style="text-align:center;">Exposure time (s)</p>'), css_class='col-md-10'),
                            css_class='form-row',
                        ),
                        Div(
                            Div(HTML('<p style="text-align:center;">B600/500nm</p>'), css_class='col-md-2'),
                            Div('b_exptime', css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                            Div(HTML('<p style="text-align:center;">R400/850nm</p>'), css_class='col-md-2'),
                            Div('r_exptime', css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                            Div(HTML('<p style="text-align:center;">Slit</p>'), css_class='col-md-12'),
                            css_class='form-row',
                        ),
                        Div(
                            Div('slit', css_class='col-md-12'), css_class='form-row'
                        ),
                        Div(
                            Div(HTML('<p style="text-align:center;">Status</p>'), css_class='col-md-12'),
                            css_class='form-row',
                        ),
                        Div(
                            Div('ready', css_class='col-md-12'), css_class='form-row'
                        ),
                        ), css_class='col-md-8'
                ), css_class='row justify-content-md-center'
            ),
            self.button_layout()
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

        if self.data['n_or_s'] == 'north':
            prog = os.getenv('GEMINI_NORTH_PROGRAMID')
            pwd = os.getenv('GEMINI_NORTH_PASSWORD')
        elif self.data['n_or_s'] == 'south':
            prog = os.getenv('GEMINI_SOUTH_PROGRAMID')
            pwd = os.getenv('GEMINI_SOUTH_PASSWORD')

        mag = self.data['mag_approx'] + '/' + self.data['mag_approx_filter'] + '/' + 'AB'

        payload = {
            'ready': self.data['ready'],
            'prog': prog,
            'email': os.getenv('GEMINI_EMAIL',''),
            'password': pwd,
            'ra': coords.ra.to_string(unit=u.hour,sep=':'),
            'dec': coords.dec.to_string(unit=u.degree,sep=':'),
            'mags': mag,
            'windowDate': now.strftime('%Y-%m-%d'),
            'windowTime': now.strftime('%H:%M:%S'),
            'windowDuration': int(float(self.data['window_size'])*24),
            'elevationType': 'airmass',
            'elevationMin': 1.0,
            'elevationMax': str(self.data['max_airmass']).strip(),
            'note': 'This observation was submitted through the API, if anything is unusual contact cmccully@lco.global',
            'posangle': 90.
        }

        return payload

    def observation_payload(self):

        target = Target.objects.get(pk=self.data['target_id'])

        if self.data['n_or_s'] == 'north':
            if self.data['slit'] == '1.5':
                obsid_map = {
                    'B600': {
                        'arc': '68',
                        'acquisition': '66',
                        'science_with_flats': '67',
                    },
                    'R400': {
                        'arc': '74',
                        'acquisition': '72',
                        'science_with_flats': '73',
                    }
                }
            elif self.data['slit'] == '1':
                obsid_map = {
                    'B600': {
                        'arc': '65',
                        'acquisition': '63',
                        'science_with_flats': '64',
                    },
                    'R400': {
                        'arc': '71',
                        'acquisition': '69',
                        'science_with_flats': '70',
                    }
                }
        elif self.data['n_or_s'] == 'south':
            if self.data['slit'] == '1.5':
                obsid_map = {
                    'B600': {
                        'arc': '64',
                        'acquisition': '65',
                        'science_with_flats': '66',
                    },
                    'R400': {
                        'arc': '70',
                        'acquisition': '71',
                        'science_with_flats': '72',
                    }
                }
            elif self.data['slit'] == '1':
                obsid_map = {
                    'B600': {
                        'arc': '61',
                        'acquisition': '62',
                        'science_with_flats': '63',
                    },
                    'R400': {
                        'arc': '67',
                        'acquisition': '68',
                        'science_with_flats': '69',
                    }
                }

        payloads = {}
        slit_width = self.data['slit']
        date_tag = datetime.utcnow().strftime('%Y%m%d')

        for color_grating in obsid_map:
            for key in obsid_map[color_grating]:
                payloads[f'{color_grating}_{key}'] = self._init_observation_payload(target)
                if self.data['n_or_s'] == 'north':
                    group = f'{target.name}: GMOS-N {color_grating} Longslit {slit_width} arcsec {date_tag}'
                elif self.data['n_or_s'] == 'south':
                    group = f'{target.name}: GMOS-S {color_grating} Longslit {slit_width} arcsec {date_tag}'
                payloads[f'{color_grating}_{key}']['group'] = group
                payloads[f'{color_grating}_{key}']['obsnum'] = obsid_map[color_grating][key]
                if key == 'arc':
                    payloads[f'{color_grating}_{key}']['target'] = 'CuAr Arc'
                elif key == 'acquisition':
                    payloads[f'{color_grating}_{key}']['target'] = 'Acquisition'
                elif key == 'science_with_flats':
                    payloads[f'{color_grating}_{key}']['target'] = target.name
                    if color_grating == 'B600':
                        payloads[f'{color_grating}_{key}']['exptime'] = int(float(self.data['b_exptime'])/2)
                    elif color_grating == 'R400':
                        payloads[f'{color_grating}_{key}']['exptime'] = int(float(self.data['r_exptime'])/2)

        # Need group in there when I'm doing it for real
        # Not sure what to do about mags for now

        return payloads


class GeminiFacility(BaseRoboticObservationFacility):
    name = 'Gemini'
    observation_types = [
        ('IMAGING_OPTICAL', 'Optical Imaging'),
        ('SPECTRA_OPTICAL', 'Optical Spectra')
    ]
    observation_forms = {
        'IMAGING_OPTICAL': OpticalImagingForm,
        'SPECTRA_OPTICAL': OpticalSpectraForm
    }

    def get_form(self, observation_type='IMAGING_OPTICAL'):
        if observation_type == 'IMAGING_OPTICAL':
            return OpticalImagingForm
        elif observation_type == 'SPECTRA_OPTICAL':
            return OpticalSpectraForm
        else:
            return OpticalSpectraForm

    @classmethod
    def submit_observation(clz, observation_payloads):

        new_observation_ids = []

        for payload in observation_payloads:
            if 'GN' in observation_payloads[payload]['prog']:
                server = os.getenv('GEMINI_NORTH_SERVER', '')
            elif 'GS' in observation_payloads[payload]['prog']:
                server = os.getenv('GEMINI_SOUTH_SERVER', '')
            url = server + '/too'
            params = observation_payloads[payload]
            response = requests.post(url, verify=False, params=params)
            print(response.url)
            try:
                response.raise_for_status()
                newobsid = response.text
                new_observation_ids.append(newobsid)
                print(newobsid + ' created and set On Hold')
            except requests.exceptions.HTTPError as exc:
                print('Request failed: ')
                print(response.content)
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
