from custom_code.models import TNSTarget
import django_filters
from django.db.models import Q
from astropy.time import Time
from datetime import datetime
from django import forms
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Submit, Layout, Div, HTML
from crispy_forms.bootstrap import PrependedAppendedText, PrependedText

class TNSTargetForm(forms.Form): 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Filter'))
        self.helper.layout = Layout(
            Div(PrependedText('name', 'Name like', placeholder='2019b')),
            Div(PrependedText('source_group', 'Discovered by', placeholder='ATLAS')),
            Div(
                Div(PrependedText('disc_mag', 'Discovery mag brighter than',
                    placeholder='19'), css_class='col-md-6'),
                Div(PrependedAppendedText('lnd_jd', 'Last non-detection within the last',
                    'days', placeholder='5'), css_class='col-md-6'),
                css_class='form-row'
            )
        )

class TNSTargetFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(field_name='name',lookup_expr='icontains',
        label='')    
    source_group = django_filters.CharFilter(field_name='source_group',lookup_expr='icontains',
        label='')
    lnd_jd = django_filters.NumberFilter(field_name='lnd_jd', method='filter_lnd_jd',
        label='')
    disc_mag = django_filters.NumberFilter(field_name='disc_mag', lookup_expr='lt',
        label='', help_text='LCO spectroscopy limit: 18.5')

    def filter_lnd_jd(self, queryset, name, value):
        jd_now = Time(datetime.utcnow()).jd
        return queryset.filter(
            Q(lnd_jd__gt=jd_now-float(value))
        )

    class Meta:
        model = TNSTarget
        fields = []
        form = TNSTargetForm
