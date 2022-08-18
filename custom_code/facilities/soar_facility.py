import copy
import requests

from tom_observations.facilities.soar import SOARFacility, SOARBaseObservationForm, SOARSpectroscopyObservationForm
from tom_observations.facilities.lco import LCOSpectroscopyObservationForm
from django import forms
import datetime
from django.conf import settings
from crispy_forms.layout import Layout, Div, HTML, Column
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText, AppendedText
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
#SPECTRAL_GRATING = 'SYZY_400'

def make_request(*args, **kwargs):
    response = requests.request(*args, **kwargs)
    if 400 <= response.status_code < 500:
        raise ImproperCredentialsException('SOAR: ' + str(response.content))
    response.raise_for_status()
    return response


class SOARObservationForm(SOARSpectroscopyObservationForm, LCOSpectroscopyObservationForm):

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
    delay_start = forms.BooleanField(required=False, label='Delay Start By')
    delay_amount = forms.FloatField(initial=0.0, min_value=0, label='', required=False)

    # These are required fields in the base LCO form, so I need to include them but will ignore
    start = forms.CharField(widget=forms.TextInput(attrs={'type': 'date'}), required=False, label='')
    end = forms.CharField(widget=forms.TextInput(attrs={'type': 'date'}), required=False, label='')
    name = forms.CharField(initial='SOAR Observation', required=False, label='')


    def filter_choices(self):
        return set([
            (f['code'], f['name']) for ins in self._get_instruments().values() for f in
            ins['optical_elements'].get('slits', [])
        ])

    def grating_choices(self):
        return set([
            (f['code'], f['name']) for ins in self._get_instruments().values() for f in 
            ins['optical_elements'].get('gratings', [])
        ])

    def readout_choices(self):
        return set([
            (f['code'], f['name']) for ins in self._get_instruments().values() for f in 
            ins['modes']['readout'].get('modes', []) if 'Image' not in f['name']
        ])


    def clean_start(self):
        # Took care of this in clean method, so ignore
        return self.cleaned_data['start']


    def clean_end(self):
        # Took care of this in clean method, so ignore
        return self.cleaned_data['end']


    def clean(self):
        cleaned_data = super().clean()
        target = Target.objects.get(pk=cleaned_data['target_id'])
        cleaned_data['name'] = target.name
        now = datetime.datetime.utcnow()
        if cleaned_data.get('delay_start'):
            cleaned_data['start'] = str(now + datetime.timedelta(days=cleaned_data['delay_amount']))
            cleaned_data['end'] = str(now + datetime.timedelta(days=cleaned_data['window']+cleaned_data['delay_amount']))
        else:
            cleaned_data['start'] = str(now)
            cleaned_data['end'] = str(now + datetime.timedelta(days=cleaned_data['window']))
        #cleaned_data['start'] = str(datetime.datetime.utcnow())
        #cleaned_data['end'] = str(datetime.datetime.utcnow() +
        #                               datetime.timedelta(days=cleaned_data['window']))
        return cleaned_data

    
    def _build_instrument_config(self):
        instrument_configs = super()._build_instrument_config()
        
        instrument_configs[0]['optical_elements'] = {
            'slit': self.cleaned_data['filter'],
            'grating': self.cleaned_data['grating']#SPECTRAL_GRATING
        }
        instrument_configs[0]['rotator_mode'] = 'SKY'
        instrument_configs[0]['mode'] = self.cleaned_data['readout']

        return instrument_configs


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['proposal'] = forms.ChoiceField(choices=self.proposal_choices(),initial='SOAR2022A-002')
        self.fields['instrument_type'] = forms.ChoiceField(choices=self.instrument_choices(), initial='SOAR_GHTS_REDCAM', label='')
        self.fields['grating'] = forms.ChoiceField(choices=self.grating_choices(), initial='400_SYGY', label='')
        self.fields['filter'] = forms.ChoiceField(choices=list(self.filter_choices()), initial=list(self.filter_choices())[0][0], label='')
        self.fields['readout'] = forms.ChoiceField(choices=self.readout_choices(), initial='GHTS_R_400m1_2x2', label='')

        for field_name in ['start', 'end', 'name', 'groups']:
            self.fields[field_name].widget = forms.HiddenInput()

        self.helper.layout = Layout(
            self.common_layout,
            Div(
                Div(
                    HTML("<p></p>"),
                    PrependedAppendedText(
                        'window','Once in the next', 'days'
                    ),
                    Div(
                        Column('delay_start'),
                        Column(AppendedText('delay_amount', 'days')),
                        css_class='form_row'
                    ),
                    PrependedText('exposure_time','Exposure Time'),
                    PrependedText('exposure_count','Exposure Count'),
                    PrependedText('rotator_angle','Rotator Angle'),
                    PrependedText('instrument_type','Camera'),
                    PrependedText('grating', 'Grating'),
                    PrependedText('filter','Slit Width'),
                    PrependedText('readout', 'Readout Mode'),
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

    observation_types = [('SPECTRA', 'Goodman Spectrograph RedCam: 1.0" slit'),
                         ('SPECTRA', 'Goodman Spectrograph BlueCam: 1.0" slit')]
    observation_forms = {'SPECTRA': SOARObservationForm}

    def get_form(self, observation_type):
        return SOARObservationForm

    def add_calibrations(self, observation_payload):
        _target = observation_payload['requests'][0]['configurations'][0]['target']
        _constraints = observation_payload['requests'][0]['configurations'][0]['constraints']
        instrument_type = observation_payload['requests'][0]['configurations'][0]['instrument_type']

        if instrument_type == 'SOAR_TRIPLESPEC':
            observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements'].pop('slit', '')
            observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements'].pop('grating', '')
            slit = ''
            grating = ''

        else:
            slit = observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['slit']
            grating = observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['optical_elements']['grating']

        rotator_angle = observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['extra_params']['rotator_angle']
        readout = observation_payload['requests'][0]['configurations'][0]['instrument_configs'][0]['mode']

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
                    'grating': grating
                },
                'mode': readout,

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

        if instrument_type != 'SOAR_TRIPLESPEC':
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
