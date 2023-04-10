from django import forms
from crispy_forms.layout import Layout, Div, Row
from crispy_forms.helper import FormHelper


class GWGalaxyObservationForm(forms.Form):

    exposure_time = forms.IntegerField(min_value=1, label='Exposure time (s)', initial=300)
    epochs = forms.IntegerField(min_value=1, label='No. of Epochs', initial=5)
    exposures_per_epoch = forms.IntegerField(min_value=1, label='No. of Exposures per Epoch', initial=1)
    ipp_value = forms.FloatField(min_value=0.5, max_value=2.0, label='IPP', initial=1.0)
    observation_mode = forms.ChoiceField(choices=(('NORMAL', 'Normal'), ('RAPID_RESPONSE', 'Rapid-Response'), ('TIME_CRITICAL', 'Time-Critical')), label='Observation Mode', initial=('RAPID_RESPONSE', 'Rapid-Response'))
    filters = forms.CharField(initial='g,i', label='Filters')
    instrument_type = forms.ChoiceField(
            choices=(('0M4-SCICAM-SBIG', '0.4 meter SBIG'), 
                     ('1M0-SCICAM-SINISTRO', '1.0 meter Sinistro'), 
                     ('2M0-SCICAM-SPECTRAL', '2.0 meter Spectral')
            ), initial=('1M0-SCICAM-SINISTRO', '1.0 meter Sinistro'),
            label='Instrument'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper(self)
        self.helper.layout = Layout(
            self.layout(),
        )

    def layout(self):

        return Div(
            Div(
                Row('exposure_time'),
                Row('epochs'),
                Row('exposures_per_epoch'),
                Row('filters'),
                css_class='col-md-6'
            ),
            Div(
                Row('ipp_value'),
                Row('instrument_type'),
                Row('observation_mode'),
                css_class='col-md-6'
            ),
        css_class='form-row'
        )
