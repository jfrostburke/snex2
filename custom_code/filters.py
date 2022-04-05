from custom_code.models import TNSTarget, ScienceTags, TargetTags, BrokerTarget
from tom_targets.models import Target, TargetList
from tom_targets.filters import filter_for_field, TargetFilter
from django.conf import settings
import django_filters
from django.db.models import ExpressionWrapper, FloatField, Q
from math import radians
from django.db.models.functions.math import ACos, Cos, Radians, Pi, Sin
from django.db.models.functions import Lower
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
            Div(
                Div(PrependedText('name', 'Name like'), css_class='col-md-4'),
                Div(PrependedText('source_group', 'Discovered by'), css_class='col-md-4'),
                Div('in_tess', css_class='col-md-4'),
                css_class='form-row'
            ),
            Div(
                Div(PrependedText('disc_mag', 'Discovery mag brighter than',
                    placeholder='19', style='color: black;'), css_class='col-md-6'),
                Div(PrependedAppendedText('lnd_jd', 'Last non-detection within the last',
                    'days', placeholder='5', style='color: black;'), css_class='col-md-6'),
                css_class='form-row'
            ),
        )

class TNSTargetFilter(django_filters.FilterSet):
    TESS_choices = [
        ('y', 'Yes'),
        ('n', 'No')
    ]
    name = django_filters.CharFilter(field_name='name',lookup_expr='icontains',
        label='')    
    source_group = django_filters.CharFilter(field_name='source_group',lookup_expr='icontains',
        label='')
    lnd_jd = django_filters.NumberFilter(field_name='lnd_jd', initial=5, method='filter_lnd_jd',
        label='')
    disc_mag = django_filters.NumberFilter(field_name='disc_mag', initial=19, lookup_expr='lt',
        label='', help_text='LCO spectroscopy limit: 18.5')
    in_tess = django_filters.ChoiceFilter(field_name='TESS_sectors', method='filter_TESS',
        label='', choices=TESS_choices, empty_label='In TESS?')

    def filter_lnd_jd(self, queryset, name, value):
        jd_now = Time(datetime.utcnow()).jd
        return queryset.filter(
            Q(lnd_jd__gt=jd_now-float(value))
        )

    def filter_TESS(self, queryset, name, value):
            print(value, type(value))
            if value == 'y':      bool_value = True
            elif value == 'n':    bool_value = False
            return queryset.filter(
                ~Q(TESS_sectors__isnull = bool_value)
            )

    class Meta:
        model = TNSTarget
        fields = []
        form = TNSTargetForm

class CustomTargetFilter(TargetFilter):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in settings.EXTRA_FIELDS:
            new_filter = filter_for_field(field)
            new_filter.parent = self
            self.filters[field['name']] = new_filter
        self.filters['sciencetags'].field.label_from_instance = lambda obj: obj.tag

    key = None
    value = None

    sciencetags = django_filters.ModelChoiceFilter(queryset=ScienceTags.objects.all().order_by(Lower('tag')), label="Science Tag", method='filter_sciencetags')

    def filter_sciencetags(self, queryset, name, value):
        return queryset.filter(targettags__tag=value).distinct()

    class Meta:
        model = Target
        fields = ['name', 'cone_search', 'targetlist__name', 'sciencetags']


class BrokerTargetForm(forms.Form): 
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.add_input(Submit('submit', 'Filter'))
        self.helper.layout = Layout(
            Div(
                Div(PrependedText('name', 'Name like'), css_class='col-md-4'),
                Div(PrependedText('stream_name', 'Name of Stream'), css_class='col-md-4'),
                Div(PrependedText('status', 'Status'), css_class='col-md-4'),
                css_class='form-row'
            ),
        )

class BrokerTargetFilter(django_filters.FilterSet):
    
    status_choices = [
        ('new', 'New'),
        ('interesting', 'Interesting'),
        ('uninteresting', 'Uninteresting')
    ]
    
    name = django_filters.CharFilter(field_name='name', lookup_expr='icontains', label='')
    stream_name = django_filters.CharFilter(field_name='stream_name', lookup_expr='icontains',
        label=''
    )
    status = django_filters.ChoiceFilter(field_name='status', method='filter_status',
        label='', choices=status_choices, empty_label='')

    def filter_status(self, queryset, name, status):
        if not status:
            status = ''
        return queryset.filter(status=status)
    
    class Meta:
        model = BrokerTarget
        fields = []
        form = BrokerTargetForm
