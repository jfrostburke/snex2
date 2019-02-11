import requests
from django.conf import settings
from django import forms
from dateutil.parser import parse
from crispy_forms.layout import Layout, Div, HTML
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText
from django.core.cache import cache
import datetime

from tom_observations.facility import GenericObservationForm
from tom_common.exceptions import ImproperCredentialsException
from tom_observations.facility import GenericObservationFacility
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

# The SITES dictionary is used to calculate visibility intervals in the
# planning tool. All entries should contain latitude, longitude, elevation
# and a code.
SITES = {
    'Siding Spring': {
        'sitecode': 'coj',
        'latitude': -31.272,
        'longitude': 149.07,
        'elevation': 1116
    },
    'Sutherland': {
        'sitecode': 'cpt',
        'latitude': -32.38,
        'longitude': 20.81,
        'elevation': 1804
    },
    'Teide': {
        'sitecode': 'tfn',
        'latitude': 20.3,
        'longitude': -16.511,
        'elevation': 2390
    },
    'Cerro Tololo': {
        'sitecode': 'lsc',
        'latitude': -30.167,
        'longitude': -70.804,
        'elevation': 2198
    },
    'McDonald': {
        'sitecode': 'elp',
        'latitude': 30.679,
        'longitude': -104.015,
        'elevation': 2027
    },
    'Haleakala': {
        'sitecode': 'ogg',
        'latitude': 20.706,
        'longitude': -156.258,
        'elevation': 3065
    }
}

# Functions needed specifically for LCO


def make_request(*args, **kwargs):
    response = requests.request(*args, **kwargs)
    if 400 <= response.status_code < 500:
        raise ImproperCredentialsException('LCO: ' + str(response.content))
    response.raise_for_status()
    return response


def _flatten_error_dict(form, error_dict):
    non_field_errors = []
    for k, v in error_dict.items():
        if type(v) == list:
            for i in v:
                if type(i) == str:
                    if k in form.fields:
                        form.add_error(k, i)
                    else:
                        non_field_errors.append('{}: {}'.format(k, i))
                if type(i) == dict:
                    non_field_errors.append(_flatten_error_dict(form, i))
        elif type(v) == str:
            if k in form.fields:
                form.add_error(k, v)
            else:
                non_field_errors.append('{}: {}'.format(k, v))
        elif type(v) == dict:
            non_field_errors.append(_flatten_error_dict(form, v))

    return non_field_errors


def _get_instruments():
    response = make_request(
        'GET',
        PORTAL_URL + '/api/instruments/',
        headers={'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}
    )
    return response.json()


def _instrument_choices():
    return [(k, k) for k in _get_instruments()]


def _filter_choices():
    return set([(f, f) for ins in _get_instruments().values() for f in ins['filters']])


def _proposal_choices():
    response = make_request(
        'GET',
        PORTAL_URL + '/api/profile/',
        headers={'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}
    )
    choices = []
    for p in response.json()['proposals']:
        if p['current']:
            choices.append((p['id'], '{} ({})'.format(p['title'], p['id'])))
    return choices


class LCOObservationForm(GenericObservationForm):
    """
    This is the class that is responsible for displaying the observation request form.
    It inherits from tom_observations.facility.GenericObservationForm which provides
    some base shared functionality. Extra fields are provided below.
    The layout is handlded by Django crispy forms which allows customizability of the
    form layout without needing to write html templates:
    https://django-crispy-forms.readthedocs.io/en/d-0/layouts.html
    See the documentation on Django forms for more information.
    """
    #group_id = forms.CharField()
    proposal = forms.ChoiceField(choices=_proposal_choices,initial='KEY2017AB-001')
    ipp_value = forms.FloatField(initial=1.0,label='')
    start = forms.CharField(initial=str(datetime.datetime.utcnow()))
    #start = forms.DateField(widget=forms.SelectDateWidget(empty_label=("Choose year","choose month","choose day")))
    end = forms.CharField(widget=forms.TextInput(attrs={'type': 'date'}))
    window = forms.FloatField(initial=3.0,label="")
    filter = forms.ChoiceField(choices=_filter_choices,initial='b')
    instrument_name = forms.ChoiceField(choices=_instrument_choices,initial='1M0-SCICAM-SINISTRO')
    exposure_count_U = forms.IntegerField(min_value=1,initial=2,label='No. of exposures')
    exposure_time_U = forms.FloatField(min_value=0.1,initial=300,label='Exposure time')
    exposure_count_B = forms.IntegerField(min_value=1,initial=2,label='')
    exposure_time_B = forms.FloatField(min_value=0.1,initial=200,label='')
    exposure_count_V = forms.IntegerField(min_value=1,initial=2,label='')
    exposure_time_V = forms.FloatField(min_value=0.1,initial=120,label='')
    exposure_count_g = forms.IntegerField(min_value=1,initial=2,label='')
    exposure_time_g = forms.FloatField(min_value=0.1,initial=200,label='')
    exposure_count_r = forms.IntegerField(min_value=1,initial=2,label='')
    exposure_time_r = forms.FloatField(min_value=0.1,initial=120,label='')
    exposure_count_i = forms.IntegerField(min_value=1,initial=2,label='')
    exposure_time_i = forms.FloatField(min_value=0.1,initial=120,label='')
    max_airmass = forms.FloatField(initial=1.6,label="")
    observation_type = forms.ChoiceField(
        choices=(('NORMAL', 'Normal'), ('TARGET_OF_OPPORTUNITY', 'Rapid Response'))
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper.layout = Layout(
            self.common_layout,
            Div(
                Div(
                    HTML("<p></p>"),
                    PrependedAppendedText(
                        'window','Once in the next', 'days'
                    ),
                    Div(
                        Div(PrependedText('exposure_time_U','U'),css_class='col-md-6'),
                        Div('exposure_count_U',css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('exposure_time_B','B'),css_class='col-md-6'),
                        Div('exposure_count_B',css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('exposure_time_V','V'),css_class='col-md-6'),
                        Div('exposure_count_V',css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('exposure_time_g','g'),css_class='col-md-6'),
                        Div('exposure_count_g',css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('exposure_time_r','r'),css_class='col-md-6'),
                        Div('exposure_count_r',css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    Div(
                        Div(PrependedText('exposure_time_i','i'),css_class='col-md-6'),
                        Div('exposure_count_i',css_class='col-md-6'),
                        css_class='form-row'
                    ),
                    css_class='col'
                ),
                Div(
                    HTML("<p></p>"),
                    PrependedText('max_airmass', 'Airmass <'),
                    PrependedText('ipp_value', 'IPP'),
                    'instrument_name', 'proposal', 'observation_type', 
                    css_class='col'
                ),
                css_class='form-row'
            )
        )

    def clean_start(self):
        start = self.cleaned_data['start']
        return parse(start).isoformat()

    def clean_end(self):
        end = self.cleaned_data['end']
        return parse(end).isoformat()

    def is_valid(self):
        super().is_valid()
        errors = LCOFacility().validate_observation(self.observation_payload)
        if errors:
            self.add_error(None, _flatten_error_dict(self, errors))
        return not errors

    def instrument_to_type(self, instrument_name):
        if any(x in instrument_name for x in ['FLOYDS', 'NRES']):
            return 'SPECTRUM'
        else:
            return 'EXPOSE'

    @property
    def observation_payload(self):
        target = Target.objects.get(pk=self.cleaned_data['target_id'])
        molecules = []
        exps = {
           'u': [self.cleaned_data['exposure_time_U'],self.cleaned_data['exposure_count_U']],
           'b': [self.cleaned_data['exposure_time_B'],self.cleaned_data['exposure_count_B']], 
           'v': [self.cleaned_data['exposure_time_V'],self.cleaned_data['exposure_count_V']], 
           'gp': [self.cleaned_data['exposure_time_g'],self.cleaned_data['exposure_count_g']], 
           'rp': [self.cleaned_data['exposure_time_r'],self.cleaned_data['exposure_count_r']], 
           'ip': [self.cleaned_data['exposure_time_i'],self.cleaned_data['exposure_count_i']]
        }
        for filt, exp_requests in exps.items():
            if 0 not in [int(x) for x in exp_requests]:
               molecules.append(
                   {
                       "type": self.instrument_to_type(self.cleaned_data['instrument_name']),
                       "instrument_name": self.cleaned_data['instrument_name'],
                       "filter": filt,
                       "spectra_slit": filt,
                       "exposure_count": exp_requests[1],
                       "exposure_time": exp_requests[0]
                   }
               )
        return {
            #"group_id": self.cleaned_data['group_id'],
            "group_id": target.name,
            "proposal": self.cleaned_data['proposal'],
            "ipp_value": self.cleaned_data['ipp_value'],
            "operator": "SINGLE",
            "observation_type": self.cleaned_data['observation_type'],
            "requests": [
                {
                    "target": {
                        "name": target.name,
                        "type": target.type,
                        "ra": target.ra,
                        "dec": target.dec,
                        "proper_motion_ra": target.pm_ra,
                        "proper_motion_dec": target.pm_dec,
                        "epoch": target.epoch,
                        "orbinc": target.inclination,
                        "longascnode": target.lng_asc_node,
                        "argofperih": target.arg_of_perihelion,
                        "perihdist": target.distance,
                        "meandist": target.semimajor_axis,
                        "meananom": target.mean_anomaly,
                        "dailymot": target.mean_daily_motion
                    },
                    "molecules": molecules,
                    "windows": [
                        {
                            #"start": self.cleaned_data['start'],
                            "start": str(datetime.datetime.utcnow()),
                            #"end": self.cleaned_data['end']
                            "end": str(datetime.datetime.utcnow()+
                                datetime.timedelta(days=self.cleaned_data['window']))
                        }
                    ],
                    "location": {
                        "telescope_class": self.cleaned_data['instrument_name'][:3].lower()
                    },
                    "constraints": {
                        "max_airmass": self.cleaned_data['max_airmass'],
                    }
                }
            ]
        }


class LCOFacility(GenericObservationFacility):
    name = 'LCO'
    form = LCOObservationForm

    def submit_observation(self, observation_payload):
        SUBMIT_URL = PORTAL_URL + '/api/userrequests/validate/'
        response = make_request(
            'POST',
            #PORTAL_URL + '/api/userrequests/',
            #Changing to validate URL while testing
            SUBMIT_URL,
            json=observation_payload,
            headers=self._portal_headers()
        )
        #return [r['id'] for r in response.json()['requests']]
        print('Observation submitted to {0}'.format(SUBMIT_URL))
        print(response.json())
        return response.json()

    def validate_observation(self, observation_payload):
        response = make_request(
            'POST',
            PORTAL_URL + '/api/userrequests/validate/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        return response.json()['errors']

    def get_observation_url(self, observation_id):
        return PORTAL_URL + '/requests/' + observation_id

    def get_terminal_observing_states(self):
        return TERMINAL_OBSERVING_STATES

    def get_observing_sites(self):
        return SITES

    def get_observation_status(self, observation_id):
        response = make_request(
            'GET',
            PORTAL_URL + '/api/requests/{0}'.format(observation_id),
            headers=self._portal_headers()
        )
        return response.json()['state']

    def data_products(self, observation_id, product_id=None):
        products = []
        for frame in self._archive_frames(observation_id, product_id):
            products.append({
                'id': frame['id'],
                'filename': frame['filename'],
                'created': parse(frame['DATE_OBS']),
                'url': frame['url']
            })
        return products

    # The following methods are used internally by this module
    # and should not be called directly from outside code.

    def _portal_headers(self):
        if LCO_SETTINGS.get('api_key'):
            return {'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}
        else:
            return {}

    def _archive_headers(self):
        if LCO_SETTINGS.get('api_key'):
            archive_token = cache.get('LCO_ARCHIVE_TOKEN')
            if not archive_token:
                response = make_request(
                    'GET',
                    PORTAL_URL + '/api/profile/',
                    headers={'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}
                )
                archive_token = response.json().get('tokens', {}).get('archive')
                if archive_token:
                    cache.set('LCO_ARCHIVE_TOKEN', archive_token, 3600)
                    return {'Authorization': 'Bearer {0}'.format(archive_token)}

            else:
                return {'Authorization': 'Bearer {0}'.format(archive_token)}
        else:
            return {}

    def _archive_frames(self, observation_id, product_id=None):
        # todo save this key somewhere
        frames = []
        if product_id:
            response = make_request(
                'GET',
                'https://archive-api.lco.global/frames/{0}/'.format(product_id),
                headers=self._archive_headers()
            )
            frames = [response.json()]
        else:
            response = make_request(
                'GET',
                'https://archive-api.lco.global/frames/?REQNUM={0}'.format(observation_id),
                headers=self._archive_headers()
            )
            frames = response.json()['results']

        return frames
