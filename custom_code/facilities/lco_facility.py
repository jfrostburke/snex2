import requests
from django.conf import settings
from django import forms
from dateutil.parser import parse
from crispy_forms.layout import Layout, Div, HTML, Column, Row
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText
from django.core.cache import cache
from astropy import units as u
import datetime

from tom_observations.facility import BaseObservationForm
from tom_common.exceptions import ImproperCredentialsException
from tom_observations.facility import BaseRoboticObservationFacility, get_service_class
from tom_targets.models import Target

from tom_observations.facilities.lco import LCOBaseObservationForm, LCOPhotometricSequenceForm, LCOSpectroscopicSequenceForm
from tom_observations.widgets import FilterField

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

# Units of flux and wavelength for converting to Specutils Spectrum1D objects
FLUX_CONSTANT = (1e-15 * u.erg) / (u.cm ** 2 * u.second * u.angstrom)
WAVELENGTH_UNITS = u.angstrom

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
    cached_instruments = cache.get('lco_instruments')

    if not cached_instruments:
        response = make_request(
            'GET',
            PORTAL_URL + '/api/instruments/',
            headers={'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}
        )
        cached_instruments = response.json()
        cache.set('lco_instruments', cached_instruments)

    return cached_instruments


def instrument_choices():
    return [(k, k) for k in _get_instruments()]


def filter_choices():
    return set([
            (f['code'], f['name']) for ins in _get_instruments().values() for f in
            ins['optical_elements'].get('filters', []) + ins['optical_elements'].get('slits', [])
            ])


def proposal_choices():
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


class LCOObservationForm(BaseObservationForm):
    #group_id = forms.CharField()
    #proposal = forms.ChoiceField(choices=_proposal_choices,initial='KEY2017AB-001')
    proposal = forms.ChoiceField(choices=proposal_choices(),initial='KEY2017AB-001')
    ipp_value = forms.FloatField(initial=1.0,label='',
        help_text='IPP: priority, ranging from 0.5 (low) to 2.0 (high)')
    start = forms.CharField(initial=str(datetime.datetime.utcnow()))
    #start = forms.DateField(widget=forms.SelectDateWidget(empty_label=("Choose year","choose month","choose day")))
    end = forms.CharField(widget=forms.TextInput(attrs={'type': 'date'}))
    window = forms.FloatField(initial=3.0,label="")
    filter = forms.ChoiceField(choices=filter_choices(),initial='b')
    instrument_type= forms.ChoiceField(choices=instrument_choices(),initial='1M0-SCICAM-SINISTRO')
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
    max_airmass = forms.FloatField(initial=1.6,label='')
    priority_level = forms.ChoiceField(
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
                    'instrument_type', 'proposal', 'priority_level', 
                    css_class='col'
                ),
                css_class='form-row'
            ),
            self.button_layout()
        )
    """
    def layout(self):
        return Div(
            Div(
                'name', 'proposal', 'ipp_value', 'observation_type', 'start', 'end',
                css_class='col'
            ),
            Div(
                'filter', 'instrument_type', 'exposure_count', 'exposure_time', 'max_airmass',
                css_class='col'
            ),
            css_class='form-row'
        )

    def extra_layout(self):
        # If you just want to add some fields to the end of the form, add them here.
        return Div()
    """
    def clean_start(self):
        start = self.cleaned_data['start']
        return parse(start).isoformat()

    def clean_end(self):
        end = self.cleaned_data['end']
        return parse(end).isoformat()

    def is_valid(self):
        super().is_valid()
        # TODO this is a bit leaky and should be done without the need of get_service_class
        obs_module = get_service_class(self.cleaned_data['facility'])
        errors = obs_module().validate_observation(self.observation_payload())
        if errors:
            self.add_error(None, _flatten_error_dict(self, errors))
        return not errors

    def instrument_to_type(self, instrument_type):
        if any(x in instrument_type for x in ['FLOYDS', 'NRES']):
            return 'SPECTRUM'
        else:
            return 'EXPOSE'

    def observation_payload(self):
        target = Target.objects.get(pk=self.cleaned_data['target_id'])
        target_fields = {
            "name": target.name,
        }
        if target.type == Target.SIDEREAL:
            target_fields['type'] = 'ICRS'
            target_fields['ra'] = target.ra
            target_fields['dec'] = target.dec
            target_fields['proper_motion_ra'] = target.pm_ra
            target_fields['proper_motion_dec'] = target.pm_dec
            target_fields['epoch'] = target.epoch
        elif target.type == Target.NON_SIDEREAL:
            target_fields['type'] = 'ORBITAL_ELEMENTS'
            target_fields['scheme'] = target.scheme
            target_fields['orbinc'] = target.inclination
            target_fields['longascnode'] = target.lng_asc_node
            target_fields['argofperih'] = target.arg_of_perihelion
            target_fields['eccentricity'] = target.eccentricity
            target_fields['meandist'] = target.semimajor_axis
            target_fields['meananom'] = target.mean_anomaly
            target_fields['perihdist'] = target.distance
            target_fields['dailymot'] = target.mean_daily_motion
            target_fields['epochofel'] = target.epoch
            target_fields['epochofperih'] = target.epoch_of_perihelion

        #photometry
        if self.instrument_to_type(self.cleaned_data['instrument_type']) == 'EXPOSE':
            exps = {
               'u': 
                    {'exp_time': self.cleaned_data['exposure_time_U'],
                    'exp_count': self.cleaned_data['exposure_count_U']},
               'B': 
                    {'exp_time': self.cleaned_data['exposure_time_B'],
                    'exp_count': self.cleaned_data['exposure_count_B']},
               'V': 
                    {'exp_time': self.cleaned_data['exposure_time_V'],
                    'exp_count': self.cleaned_data['exposure_count_V']},
               'gp': 
                    {'exp_time': self.cleaned_data['exposure_time_g'],
                    'exp_count': self.cleaned_data['exposure_count_g']},
               'rp': 
                    {'exp_time': self.cleaned_data['exposure_time_r'],
                    'exp_count': self.cleaned_data['exposure_count_r']},
               'ip': 
                    {'exp_time': self.cleaned_data['exposure_time_i'],
                    'exp_count': self.cleaned_data['exposure_count_i']}
            }
            configurations = []
            for filt in exps:
                configurations.append(
                        {
                            "type": self.instrument_to_type(self.cleaned_data['instrument_type']),
                            "instrument_type": self.cleaned_data['instrument_type'],
                            "target": target_fields,
                            "instrument_configs": [
                                {
                                    "exposure_count": exps[filt]['exp_count'],
                                    "exposure_time": exps[filt]['exp_time'],
                                    "optical_elements": {"filter": filt}
                                }
                            ],
                            "acquisition_config": {

                            },
                            "guiding_config": {

                            },
                            "constraints": {
                               "max_airmass": self.cleaned_data['max_airmass'],
                            }
                        }
                )
                
        else:
            optical_elements = {
                "slit": self.cleaned_data['filter'],
            }

        return {
            #"name": self.cleaned_data['name'],
            "name": target.name,
            "proposal": self.cleaned_data['proposal'],
            "ipp_value": self.cleaned_data['ipp_value'],
            "operator": "SINGLE",
            "observation_type": self.cleaned_data['priority_level'],
            "requests": [
                {
                    "configurations": configurations,
                    "windows": [
                        {
                            #"start": self.cleaned_data['start'],
                            #"end": self.cleaned_data['end']
                            "start": str(datetime.datetime.utcnow()),
                            "end": str(datetime.datetime.utcnow()+
                                datetime.timedelta(days=self.cleaned_data['window']))
                        }
                    ],
                    "location": {
                        "telescope_class": self.cleaned_data['instrument_type'][:3].lower()
                    }
                }
            ]
        }



class InitialValue:
    exposure_count = 2
    block_num = 1

    def __init__(self, filt):
        self.exposure_time = self.get_values_from_filt(filt)

    def get_values_from_filt(self, filt):
        initial_exp_times = {'U': 300, 'B': 200, 'V': 120, 'g': 200, 'r': 120, 'i': 120}
        return initial_exp_times.get(filt, 0)


class SnexPhotometricSequenceForm(LCOPhotometricSequenceForm):
    name = forms.CharField(required=False)
    ipp_value = forms.FloatField(label='Intra Proposal Priority (IPP factor)',
                                 min_value=0.5,
                                 max_value=2,
                                 initial=1.0)
    #TODO: Rewrite layout to include these custom field names
    phot_max_airmass = forms.FloatField(initial=1.6, min_value=0, label='Max Airmass')
    phot_min_lunar_distance = forms.IntegerField(min_value=0, label='Minimum Lunar Distance', initial=20, required=False)
    phot_cadence_frequency = forms.FloatField(required=True, min_value=0.0, initial=3.0, help_text='Days', label='')

    def __init__(self, *args, **kwargs):
        super(LCOPhotometricSequenceForm, self).__init__(*args, **kwargs)

        # Add fields for each available filter as specified in the filters property
        for filter_name in self.filters:
            self.fields[filter_name] = FilterField(label=filter_name, initial=InitialValue(filter_name), required=False)
        
        # Massage cadence form to be SNEx-styled
        self.fields['phot_cadence_strategy'] = forms.ChoiceField(
            choices=[('', 'Once in the next'), ('ResumeCadenceAfterFailureStrategy', 'Repeating every')],
            required=False,
            label=''
        )
        for field_name in ['exposure_time', 'exposure_count', 'start', 'end', 'filter']:
            self.fields.pop(field_name)
        if self.fields.get('groups'):
            self.fields['groups'].label = 'Data granted to'
        self.fields['instrument_type'] = forms.ChoiceField(choices=self.instrument_choices(), initial=('1M0-SCICAM-SINISTRO', '1.0 meter Sinistro'))
        self.fields['name'].widget = forms.HiddenInput()
        
        self.helper.layout = Layout(
            Div(
                Column('name'),
                Column('phot_cadence_strategy'),
                Column('phot_cadence_frequency'),
                css_class='form-row'
            ),
            Layout('facility', 'target_id', 'observation_type'),
            self.layout(),
            self.button_layout()
        )

    def clean(self):
        """
        This clean method does the following:
            - Adds a start time of "right now", as the photometric sequence form does not allow for specification
              of a start time.
            - Adds an end time that corresponds with the cadence frequency
            - Adds the cadence strategy to the form if "repeat" was the selected "cadence_type". If "once" was
              selected, the observation is submitted as a single observation.
        """
        #TODO: Make sure that my conversion from days to hours works,
        #      and look into implementing a "delay start by" option like in SNEx
        cleaned_data = super().clean()
        now = datetime.now()
        cleaned_data['start'] = datetime.strftime(now, '%Y-%m-%dT%H:%M:%S')
        cleaned_data['end'] = datetime.strftime(now + timedelta(hours=cleaned_data['phot_cadence_frequency']*24),
                                                '%Y-%m-%dT%H:%M:%S')

        return cleaned_data
        

class LCOFacility(BaseRoboticObservationFacility):
    name = 'LCO'
    #form = LCOObservationForm
    form = SnexPhotometricSequenceForm
    observation_types = [('IMAGING', 'Imaging'),
                         ('SPECTRA', 'Spectra')]
    observation_forms = {
        'IMAGING': SnexPhotometricSequenceForm,
        'SPECTRA': LCOSpectroscopicSequenceForm
    }

    def get_form(self, observation_type):
        return self.observation_forms.get(observation_type, LCOBaseObservationForm) #SnexPhotometricSequenceForm

    def submit_observation(self, observation_payload):
        response = make_request(
            'POST',
            PORTAL_URL + '/api/requestgroups/validate/',
            #PORTAL_URL + '/api/requestgroups/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        #return [r['id'] for r in response.json()['requests']]
        #Since we're not actually submitting just generate random id
        import random; id_number = random.randint(1,1000001)
        return [id_number]
    
    def validate_observation(self, observation_payload):
        response = make_request(
            'POST',
            PORTAL_URL + '/api/requestgroups/validate/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        return response.json()['errors']

    def get_observation_url(self, observation_id):
        return PORTAL_URL + '/requests/' + observation_id

    def get_flux_constant(self):
        return FLUX_CONSTANT

    def get_wavelength_units(self):
        return WAVELENGTH_UNITS

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
        state = response.json()['state']

        response = make_request(
            'GET',
            PORTAL_URL + '/api/requests/{0}/observations/'.format(observation_id),
            headers=self._portal_headers()
        )
        blocks = response.json()
        current_block = None
        for block in blocks:
            if block['state'] == 'COMPLETED':
                current_block = block
                break
            elif block['state'] == 'PENDING':
                current_block = block
        if current_block:
            scheduled_start = current_block['start']
            scheduled_end = current_block['end']
        else:
            scheduled_start, scheduled_end = None, None

        return {'state': state, 'scheduled_start': scheduled_start, 'scheduled_end': scheduled_end}

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
