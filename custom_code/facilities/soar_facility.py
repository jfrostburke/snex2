import copy

from tom_observations.facilities.soar import SOARFacility, SOARBaseObservationForm
from tom_observations.facilities.lco import LCOSpectroscopyObservationForm, make_request
from django import forms
import datetime
from django.conf import settings
from crispy_forms.layout import Layout, Div, HTML
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText
from tom_targets.models import Target

# Determine settings for this module.
try:
    LCO_SETTINGS = settings.FACILITIES['LCO']
except (AttributeError, KeyError):
    LCO_SETTINGS = {
        'portal_url': 'https://observe.lco.global',
        'api_key': '',
    }

# Module specific settings.
PORTAL_URL = LCO_SETTINGS['portal_url']
TERMINAL_OBSERVING_STATES = ['COMPLETED', 'CANCELED', 'WINDOW_EXPIRED']

# There is currently only one available grating, which is required for spectroscopy.
SPECTRAL_GRATING = 'SYZY_400'

class SOARObservationForm(SOARBaseObservationForm, LCOSpectroscopyObservationForm):

    # Auto set name, need to check exp getting submitted correctly
    #   Use validate endpoint to check, print submission
    # Field for exp time, exp count, rotator angle

    window = forms.FloatField(initial=3.0,label='',min_value=0.0)
    ipp_value = forms.FloatField(initial=1.0,label='',min_value=0.5,max_value=2.0)
    max_airmass = forms.FloatField(initial=1.6,label='',min_value=1.0)
    rotator_angle= forms.FloatField(initial=0.0,label='',min_value=0.0)
    exposure_count = forms.IntegerField(initial=1,label='',min_value=1)
    exposure_time = forms.FloatField(min_value=0.1,label='',
                                     widget=forms.TextInput(attrs={'placeholder': 'Seconds'}))
    observation_mode= forms.ChoiceField(
        choices=(('NORMAL', 'Normal'), ('TARGET_OF_OPPORTUNITY', 'Rapid Response')),
        label='Priority'
    )

    def filter_choices(self):
        return set([
            (f['code'], f['name']) for ins in self._get_instruments().values() for f in
            ins['optical_elements'].get('slits', [])
        ])

    def clean(self):
        cleaned_data = super().clean()
        target = Target.objects.get(pk=cleaned_data['target_id'])
        cleaned_data['name'] = target.name
        cleaned_data['start'] = str(datetime.datetime.utcnow())
        cleaned_data['end'] = str(datetime.datetime.utcnow() +
                                       datetime.timedelta(days=cleaned_data['window']))
        cleaned_data['instrument_type'] = self.instrument_choices()[0][0] # Only Goodman Redcam
        cleaned_data['filter'] = list(self.filter_choices())[0][0] # Only 1.0" slit

    def _build_instrument_config(self):
        instrument_configs = super()._build_instrument_config()

        instrument_configs[0]['optical_elements'] = {
            'slit': self.cleaned_data['filter'],
            'grating': SPECTRAL_GRATING
        }
        instrument_configs[0]['rotator_mode'] = 'SKY'

        return instrument_configs


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proposal'] = forms.ChoiceField(choices=self.proposal_choices(),initial='TOM2020A-002')
        self.helper.layout = Layout(
            self.common_layout,
            Div(
                Div(
                    HTML("<p></p>"),
                    PrependedAppendedText(
                        'window','Once in the next', 'days'
                    ),
                    PrependedText('exposure_time','Exposure Time'),
                    PrependedText('exposure_count','Exposure Count'),
                    PrependedText('rotator_angle','Rotator Angle'),
                    css_class='col'
                ),
                Div(
                    HTML("<p></p>"),
                    PrependedText('max_airmass', 'Airmass <'),
                    PrependedText('ipp_value', 'IPP'),
                    'proposal',
                    'observation_mode',
                    css_class='col'
                ),
                css_class='form-row',
            ),
            self.button_layout()
        )


class SOARFacility(SOARFacility):

    observation_types = [('SPECTRA', 'Goodman Spectrograph RedCam: 1.0" slit')]

    def get_form(self, observation_type):
        return SOARObservationForm

    def add_calibrations(self, observation_payload):
        _target = observation_payload['requests'][0]['configurations'][0]['target']
        _constraints = observation_payload['requests'][0]['configurations'][0]['constraints']
        instrument_type = observation_payload['requests'][0]['configurations'][0]['instrument_type']
        rotator_angle= observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['rotator_angle']
        slit= observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit']

        template_calibration= {
            "instrument_type": instrument_type,
            "instrument_configs": [{
                "exposure_count": 1,
                "rotator_mode": "SKY",
                "extra_params": {
                    "rotator_angle": rotator_angle
                },
                'optical_elements': {
                    'slit': slit,
                    'grating': SPECTRAL_GRATING
                },

            }],
            'acquisition_config': {
                "mode": "OFF"
            },
            'guiding_config': {
                "mode": "ON",
            },
            'target': _target,
            'constraints': _constraints
        }

        arc = copy.deepcopy(template_calibration)
        arc["type"] = "ARC"
        arc["instrument_configs"][0]["exposure_time"] = 0.5
        observation_payload['requests'][0]['configurations'].append(arc)

        flat = copy.deepcopy(template_calibration)
        flat["type"] = "LAMP_FLAT"
        flat["instrument_configs"][0]["exposure_time"] = 2
        observation_payload['requests'][0]['configurations'].append(flat)

        return observation_payload

    def validate_observation(self, observation_payload):
        observation_payload = self.add_calibrations(observation_payload)
        response = make_request(
            'POST',
            PORTAL_URL + '/api/requestgroups/validate/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        return response.json()['errors']

    def submit_observation(self, observation_payload):
        observation_payload = self.add_calibrations(observation_payload)
        response = make_request(
            'POST',
            PORTAL_URL + '/api/requestgroups/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        return [r['id'] for r in response.json()['requests']]
