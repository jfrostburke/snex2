import requests
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


def obs_choices():
    choices = []
    for p in GEM_SETTINGS['programs']:
        for obs in GEM_SETTINGS['programs'][p]:
            obsid = p + '-' + obs
            val = p.split('-')
            showtext = val[0][1] + val[1][2:] + val[2] + val[3] + ' - ' + GEM_SETTINGS['programs'][p][obs]
            choices.append((obsid, showtext))
    return choices


def get_site_code_from_program(program_id):
    return program_id.split('-')[0]


def isodatetime(value):
    isostring = parse(value).isoformat()
    ii = isostring.find('T')
    date = isostring[0:ii]
    time = isostring[ii + 1:]
    return date, time


class SNExGeminiObservationForm(GenericObservationForm):
    telescope = forms.ChoiceField(choices=(('north', 'Gemini North'), ('south', 'Gemini South')))

    observation_type = forms.ChoiceField(choices=(('gmos_imaging', 'GMOS Optical Imaging'), ('gmos_spectra', 'GMOS Optical Spectra')), label='Observation Type')
    window_size = forms.FloatField(label='', initial=1.0)
    max_airmass = forms.FloatField(min_value=1.0, max_value=5.0, initial=2.0)

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
   
    #IR imaging 
    ir_phot_exptime_choices = (
        (0, 0.0),
        (120, 120.0),
        (240, 240.0),
        (600, 600.0),
        (1200, 1200.0),
    )
    
    j_exptime = forms.ChoiceField(choices=ir_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    h_exptime = forms.ChoiceField(choices=ir_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    k_exptime = forms.ChoiceField(choices=ir_phot_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')

    ##Optical spectra
    optical_spec_exptime_choices = (
        (0, 0.0),
        (1200, 1200.0),
        (1500, 1500.0),
        (1700, 1700.0),
    )
    
    b600_exptime = forms.ChoiceField(choices=optical_spec_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    r400_exptime = forms.ChoiceField(choices=optical_spec_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')

    ##IR spectra
    jh_spec_exptime_choices = (
        (0, 0.0),
        (900, 900.0),
        (1800, 1800.0),
        (4800, 4800.0),
    )
    hk_spec_exptime_choices = (
        (0, 0.0),
        (900, 900.0),
        (1800, 1800.0),
    )

    jh_exptime = forms.ChoiceField(choices=jh_spec_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')
    hk_exptime = forms.ChoiceField(choices=hk_spec_exptime_choices, initial=0, widget=forms.Select(), required=True, label='')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            self.common_layout,
            Div(
              Div(
                Div(
                    Div(HTML('<h5 style="text-align:center";>Optical Imaging</h5>')),
                    Div(HTML("<p></p>"),
                        PrependedAppendedText(
                            'window_size', 'Once in the next', 'days'
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
                    ), css_class='col-md-5'
                ),
                Div(HTML('<p></p>'), css_class='col-md-2'),
                Div(
                    Div(HTML('<h5 style="text-align:center";>IR Imaging</h5>')),
                    Div(HTML("<p></p>"),
                        PrependedAppendedText(
                            'window_size', 'Once in the next', 'days'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">J</p>'),css_class='col-md-2'),
                          Div('j_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">H</p>'),css_class='col-md-2'),
                          Div('h_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">K</p>'),css_class='col-md-2'),
                          Div('k_exptime',css_class='col-md-10'), css_class='form-row'
                        ),
                    ), css_class='col-md-5'
                ), css_class='form-row'
              ),
              Div(
                Div(
                    Div(HTML('<h5 style="text-align:center";>Optical Spectra</h5>')),
                    Div(HTML("<p></p>"),
                        PrependedAppendedText(
                            'window_size', 'Once in the next', 'days'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">B600/500nm</p>'),css_class='col-md-4'),
                          Div('b600_exptime',css_class='col-md-8'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">R400/850nm</p>'),css_class='col-md-4'),
                          Div('r400_exptime',css_class='col-md-8'), css_class='form-row'
                        ),
                    ), css_class='col-md-5'
                ),
                Div(HTML('<p></p>'), css_class='col-md-2'),
                Div(
                    Div(HTML('<h5 style="text-align:center";>IR Spectra</h5>')),
                    Div(HTML("<p></p>"),
                        PrependedAppendedText(
                            'window_size', 'Once in the next', 'days'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">321/mm / JH</p>'),css_class='col-md-4'),
                          Div('jh_exptime',css_class='col-md-8'), css_class='form-row'
                        ),
                        Div(
                          Div(HTML('<p style="text-align:center;">321/mm / HK</p>'),css_class='col-md-4'),
                          Div('hk_exptime',css_class='col-md-8'), css_class='form-row'
                        ),
                    ), css_class='col-md-5'
                ), css_class='form-row'
              ),
            )
        )
        """
                    Div(
                        Div(PrependedText('g_exptime', 'g'), css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('r_exptime', 'r'), css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('i_exptime', 'i'), css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('z_exptime', 'z'), css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    css_class='col'
                    ),
                Div(
                    HTML("<p></p>"),
                    PrependedText('max_airmass', 'Airmass <'),
                    css_class='col'
                ),
                css_class='form-row'
            )
        )
        """

    def is_valid(self):
        super().is_valid()
        errors = SNExGemini.validate_observation(self.observation_payload)
        if errors:
            self.add_error(None, errors)
        return not errors

    def _init_observation_payload(self):

        payload = {
            "prog": progid,
            # "password": self.cleaned_data['userkey'],
            "password": SNEX_GEMINI_SETTINGS['api_key'][get_site(self.cleaned_data['obsid'])],
            # "email": self.cleaned_data['email'],
            "email": GEM_SETTINGS['user_email'],
            "obsnum": obsnum,
            "target": target.name,
            "ra": target.ra,
            "dec": target.dec,
            "note": self.cleaned_data['note'],
            "ready": True
        }
        return payload

    @property
    def observation_payload(self):
        target = Target.objects.get(pk=self.cleaned_data['target_id'])
        payloads = []
        if self.cleaned_data['observation_type'] == 'gmos_imaging':
            for f in ['g', 'r', 'i', 'z']:
                if self.cleaned_data[f + '_exptime'] > 0.0:
                    # create the program level payload (username password etc)
                    payload = self._init_observation_payload()
                    # find the science observation ID for that observation
                    # make
                    # Add the exposure time to the payload (divided by 4 because of 4 dither positions)
                    pass

        ii = self.cleaned_data['obsid'].rfind('-')
        progid = self.cleaned_data['obsid'][0:ii]
        obsnum = self.cleaned_data['obsid'][ii + 1:]


        if self.cleaned_data['brightness'] != None:
            smags = str(self.cleaned_data['brightness']).strip() + '/' + \
                    self.cleaned_data['brightness_band'] + '/' + \
                    self.cleaned_data['brightness_system']
            payload["mags"] = smags

        if self.cleaned_data['group'].strip() != '':
            payload['group'] = self.cleaned_data['group'].strip()

        # timing window?
        if self.cleaned_data['window_start'].strip() != '':
            wdate, wtime = isodatetime(self.cleaned_data['window_start'])
            payload['windowDate'] = wdate
            payload['windowTime'] = wtime
            payload['windowDuration'] = str(self.cleaned_data['window_duration']).strip()

        # airmass
        payload['elevationType'] = 'airmass'
        payload['elevationMin'] = '1.0'
        payload['elevationMax'] = str(self.cleaned_data['max_airmass']).strip()

        return payload


class GeminiFacility(GenericObservationFacility):
    name = 'Gemini'
    form = SNExGeminiObservationForm

    @classmethod
    def submit_observation(clz, observation_payloads):
        new_observation_ids = []
        for observation_payload in observation_payloads:
            response = requests.post(PORTAL_URL[get_site_code_from_program(observation_payload['prog'])] ,
                                     verify=False, params=observation_payload)
            # Note this assumes that if there is an error with the api, it will happen on the first payload
            # If it happens on a later payload, we could end up with partially submitted requests
            # we could in principle try to roll back the successful calls using the observation ids we just got.
            response.raise_for_status()
            # Return just observation number
            new_observation_ids.append(response.text)

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
        return ''

    @classmethod
    def data_products(clz, observation_record, product_id=None):
        return []
