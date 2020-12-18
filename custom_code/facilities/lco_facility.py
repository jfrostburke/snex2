import requests
from django.conf import settings
from django import forms
from dateutil.parser import parse
from crispy_forms.layout import Layout, Div, HTML, Column, Row, ButtonHolder, Submit
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText, AppendedText
from django.core.cache import cache
from astropy import units as u
import datetime

from tom_observations.facility import BaseObservationForm
from tom_common.exceptions import ImproperCredentialsException
from tom_observations.facility import BaseRoboticObservationFacility, get_service_class
from tom_targets.models import Target

from tom_observations.facilities.lco import LCOBaseObservationForm, LCOPhotometricSequenceForm, LCOSpectroscopicSequenceForm, LCOFacility
from tom_observations.widgets import FilterField
from django.contrib.auth.models import Group
from crispy_forms.helper import FormHelper

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


class InitialValue:
    exposure_count = 2
    block_num = 1

    def __init__(self, filt):
        self.exposure_time = self.get_values_from_filt(filt)

    def get_values_from_filt(self, filt):
        initial_exp_times = {'U': 300, 'B': 200, 'V': 120, 'gp': 200, 'rp': 120, 'ip': 120}
        return initial_exp_times.get(filt, 0)


class SnexPhotometricSequenceForm(LCOPhotometricSequenceForm):
    name = forms.CharField()
    ipp_value = forms.FloatField(label='Intra Proposal Priority (IPP factor)',
                                 min_value=0.5,
                                 max_value=2,
                                 initial=1.0)
    
    # Rewrite a lot of the form fields to have unique IDs between photometry and spectroscopy
    filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
    max_airmass = forms.FloatField(initial=1.6, min_value=0, label='Max Airmass')
    min_lunar_distance = forms.IntegerField(min_value=0, label='Minimum Lunar Distance', initial=20, required=False)
    cadence_frequency = forms.FloatField(required=True, min_value=0.0, initial=3.0, label='')
    ipp_value = forms.FloatField(label='IPP', min_value=0.5, max_value=2.0, initial=1.0)
    observation_mode = forms.ChoiceField(choices=(('NORMAL', 'Normal'), ('RAPID_RESPONSE', 'Rapid-Response'), ('TIME_CRITICAL', 'Time-Critical')), label='Observation Mode')
    

    def __init__(self, *args, **kwargs):
        super(LCOPhotometricSequenceForm, self).__init__(*args, **kwargs)

        # Add fields for each available filter as specified in the filters property
        for filter_name in self.filters:
            self.fields[filter_name] = FilterField(label='', initial=InitialValue(filter_name), required=False)        

        # Set default proposal to GSP
        proposal_choices = self.proposal_choices()
        initial_proposal = ''
        for choice in proposal_choices:
            if 'Global Supernova Project' in choice[1]:
                initial_proposal = choice
        self.fields['proposal'] = forms.ChoiceField(choices=proposal_choices, initial=initial_proposal)
    
        # Massage cadence form to be SNEx-styled
        self.fields['name'].label = ''
        self.fields['name'].widget.attrs['placeholder'] = 'Name'
        self.fields['cadence_strategy'] = forms.ChoiceField(
            choices=[('', 'Once in the next'), ('ResumeCadenceAfterFailureStrategy', 'Repeating every')],
            required=False,
            label=''
        )
        for field_name in ['exposure_time', 'exposure_count', 'start', 'end', 'filter']:
            self.fields.pop(field_name)
        
        if not settings.TARGET_PERMISSIONS_ONLY:
            self.fields['groups'] = forms.ModelMultipleChoiceField(
                    Group.objects.none(), 
                    required=False,
                    widget=forms.CheckboxSelectMultiple, 
                    label='Data granted to')
        
        self.fields['instrument_type'] = forms.ChoiceField(choices=self.instrument_choices(), initial=('1M0-SCICAM-SINISTRO', '1.0 meter Sinistro'))
        #self.fields['name'].widget = forms.HiddenInput()
        #self.fields['proposal'] = forms.ChoiceField(choices=self.proposal_choices(), label='Proposal')
        
        self.helper.layout = Layout(
            Div(
                Column('name'),
                Column('cadence_strategy'),
                Column(AppendedText('cadence_frequency', 'Days')),
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
        now = datetime.datetime.now()
        cleaned_data['start'] = datetime.datetime.strftime(now, '%Y-%m-%dT%H:%M:%S')
        cleaned_data['end'] = datetime.datetime.strftime(now + datetime.timedelta(hours=cleaned_data['cadence_frequency']*24),
                                                '%Y-%m-%dT%H:%M:%S')

        return cleaned_data

    def layout(self):
        if settings.TARGET_PERMISSIONS_ONLY:
            groups = Div()
        else:
            groups = Row('groups')

        # Add filters to layout
        filter_layout = Layout(
            Row(
                Column(HTML('Exposure Time')),
                Column(HTML('No. of Exposures')),
                Column(HTML('Block No.')),
            )
        )
        for filter_name in self.filters:
            filter_layout.append(Row(PrependedText(filter_name, filter_name)))
        return Div(
            Div(
                filter_layout,
                css_class='col-md-6'
            ),
            Div(
                Row('max_airmass'),
                Row(
                    PrependedText('min_lunar_distance', '>')
                ),
                Row('instrument_type'),
                Row('proposal'),
                Row('observation_mode'),
                Row('ipp_value'),
                groups,
                css_class='col-md-6'
            ),
            css_class='form-row'
        )

    def button_layout(self):
        target_id = self.initial.get('target_id')
        return ButtonHolder(
                Submit('submit', 'Submit', css_id='phot-submit')
                #HTML(f'''<a class="btn btn-outline-primary" href={{% url 'tom_targets:detail' {target_id} %}}>
                #         Back</a>''')
            )


class SnexSpectroscopicSequenceForm(LCOSpectroscopicSequenceForm):
    exposure_count = forms.IntegerField(min_value=1, required=False, initial=1, widget=forms.HiddenInput())
    cadence_frequency = forms.FloatField(required=True, min_value=0.0, initial=3.0, widget=forms.NumberInput(attrs={'placeholder': 'Days'}), label='')
    max_airmass = forms.FloatField(initial=1.6, min_value=0, label='Max Airmass')
    acquisition_radius = forms.FloatField(min_value=0, required=False, initial=5.0)
    guider_exposure_time = forms.FloatField(min_value=0, initial=10.0)
    name = forms.CharField()
    ipp_value = forms.FloatField(label='Intra Proposal Priority (IPP factor)',
                                 min_value=0.5,
                                 max_value=2,
                                 initial=1.0)
    min_lunar_distance = forms.IntegerField(min_value=0, label='Minimum Lunar Distance', initial=20, required=False)
    exposure_time = forms.IntegerField(min_value=1,
                                     widget=forms.TextInput(attrs={'placeholder': 'Seconds'}),
                                     initial=1800)
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Massage cadence form to be SNEx-styled
        self.fields['filter'] = forms.ChoiceField(choices=self.filter_choices(), 
                                                  label='Slit',
                                                  initial=('slit_2.0as', '2.0 arcsec slit'))
        self.fields['name'].label = ''
        self.fields['name'].widget.attrs['placeholder'] = 'Name'
        self.fields['min_lunar_distance'].widget.attrs['placeholder'] = 'Degrees'
        self.fields['cadence_strategy'] = forms.ChoiceField(
            choices=[('', 'Once in the next'), ('ResumeCadenceAfterFailureStrategy', 'Repeating every')],
            required=False,
            label=''
        )
        self.fields['instrument_type'] = forms.ChoiceField(choices=self.instrument_choices(),
                                                           required=False,
                                                           initial='2M0-FLOYDS-SCICAM',
                                                           widget=forms.HiddenInput())

        # Set default proposal to GSP
        proposal_choices = self.proposal_choices()
        initial_proposal = ''
        for choice in proposal_choices:
            if 'Global Supernova Project' in choice[1]:
                initial_proposal = choice
        self.fields['proposal'] = forms.ChoiceField(choices=proposal_choices, initial=initial_proposal)

        # Remove start and end because those are determined by the cadence
        for field_name in ['start', 'end']:
            if self.fields.get(field_name):
                #TODO: Figure out why start and end aren't fields sometimes
                self.fields.pop(field_name)
        if self.fields.get('groups'):
            self.fields['groups'].label = 'Data granted to'
        
        self.helper.layout = Layout(
            Div(
                Column('name'),
                Column('cadence_strategy'),
                Column(AppendedText('cadence_frequency', 'Days')),
                css_class='form-row'
            ),
            Layout('facility', 'target_id', 'observation_type'),
            self.layout(),
            self.button_layout()
        )

    def clean(self):
        """
        This clean method does the following:
            - Hardcodes instrument type as "2M0-FLOYDS-SCICAM" because it's the only instrument this form uses
            - Adds a start time of "right now", as the spectroscopic sequence form does not allow for specification
              of a start time.
            - Adds an end time that corresponds with the cadence frequency
            - Adds the cadence strategy to the form if "repeat" was the selected "cadence_type". If "once" was
              selected, the observation is submitted as a single observation.
        """
        cleaned_data = super().clean()
        self.cleaned_data['instrument_type'] = '2M0-FLOYDS-SCICAM'  # SNEx only submits spectra to FLOYDS
        now = datetime.datetime.now()
        cleaned_data['start'] = datetime.datetime.strftime(now, '%Y-%m-%dT%H:%M:%S')
        cleaned_data['end'] = datetime.datetime.strftime(now + datetime.timedelta(hours=cleaned_data['cadence_frequency']*24),
                                                '%Y-%m-%dT%H:%M:%S')

        return cleaned_data


class SnexLCOFacility(LCOFacility):
    name = 'LCO'
    observation_types = [('IMAGING', 'Imaging'),
                         ('SPECTRA', 'Spectra')]
    observation_forms = {
        'IMAGING': SnexPhotometricSequenceForm,
        'SPECTRA': SnexSpectroscopicSequenceForm
    }

    def submit_observation(self, observation_payload):
        response = make_request(
            'POST',
            #PORTAL_URL + '/api/requestgroups/validate/',
            PORTAL_URL + '/api/requestgroups/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        print('Made request')
        import pdb
        pdb.set_trace()
        return [r['id'] for r in response.json()['requests']]

    def validate_observation(self, observation_payload):
        response = make_request(
            'POST',
            PORTAL_URL + '/api/requestgroups/validate/',
            json=observation_payload,
            headers=self._portal_headers()
        )
        print('Validating observation')
        import pdb
        pdb.set_trace()
        return response.json()['errors']

