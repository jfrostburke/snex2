from custom_code.models import TNSTarget, ScienceTags, TargetTags
from tom_targets.models import Target, TargetList#
from tom_targets.filters import filter_for_field#
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
                    placeholder='19'), css_class='col-md-6'),
                Div(PrependedAppendedText('lnd_jd', 'Last non-detection within the last',
                    'days', placeholder='5'), css_class='col-md-6'),
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
    lnd_jd = django_filters.NumberFilter(field_name='lnd_jd', method='filter_lnd_jd',
        label='')
    disc_mag = django_filters.NumberFilter(field_name='disc_mag', lookup_expr='lt',
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

class CustomTargetFilter(django_filters.FilterSet):
    #key = django_filters.CharFilter(field_name='targetextra__key', label='Key')
    #value = django_filters.CharFilter(field_name='targetextra__value', label='Value')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in settings.EXTRA_FIELDS:
            new_filter = filter_for_field(field)
            new_filter.parent = self
            self.filters[field['name']] = new_filter
        self.filters['sciencetags'].field.label_from_instance = lambda obj: obj.tag

    name = django_filters.CharFilter(method='filter_name', label='Name')

    def filter_name(self, queryset, name, value):
        return queryset.filter(Q(name__icontains=value) | Q(aliases__name__icontains=value)).distinct()

    cone_search = django_filters.CharFilter(method='filter_cone_search', label='Cone Search',
                                            help_text='RA, Dec, Search Radius (degrees)')

    target_cone_search = django_filters.CharFilter(method='filter_cone_search', label='Cone Search (Target)',
                                                   help_text='Target Name, Search Radius (degrees)')

    def filter_cone_search(self, queryset, name, value):
        if name == 'cone_search':
            ra, dec, radius = value.split(',')
        elif name == 'target_cone_search':
            target_name, radius = value.split(',')
            targets = Target.objects.filter(
                Q(name__icontains=target_name) | Q(aliases__name__icontains=target_name)
            ).distinct()
            if len(targets) == 1:
                ra = targets[0].ra
                dec = targets[0].dec
            else:
                return queryset.filter(name=None)

        ra = float(ra)
        dec = float(dec)

        double_radius = float(radius) * 2
        queryset = queryset.filter(ra__gte=ra - double_radius, ra__lte=ra + double_radius,
                                   dec__gte=dec - double_radius, dec__lte=dec + double_radius)

        separation = ExpressionWrapper(
            180 * ACos(
                (Sin(radians(dec)) * Sin(Radians('dec'))) +
                (Cos(radians(dec)) * Cos(Radians('dec')) * Cos(radians(ra) - Radians('ra')))
            ) / Pi(), FloatField()
        )

        return queryset.annotate(separation=separation).filter(separation__lte=radius)
#        half_pi = 90
#
#        separation = ExpressionWrapper(
#            ACos(
#                (Cos(half_pi - float(dec)) * Cos(half_pi - F('dec'))) +
#                (Sin(half_pi - float(dec)) * Sin(half_pi - F('dec')) * Cos(float(ra) - F('ra')))
#            ), FloatField()
#        )
#
#        return queryset.annotate(separation=separation).filter(separation__lte=radius)

    def filter_target_cone_search(self, queryset, name, value):
        return queryset

    # hide target grouping list if user not logged in
    def get_target_list_queryset(request):
        if request.user.is_authenticated:
            return TargetList.objects.all()
        else:
            return TargetList.objects.none()

    targetlist__name = django_filters.ModelChoiceFilter(queryset=get_target_list_queryset, label=    "Target Grouping")

    sciencetags = django_filters.ModelChoiceFilter(queryset=ScienceTags.objects.all().order_by(Lower('tag')), label="Science Tag", method='filter_sciencetags')

    def filter_sciencetags(self, queryset, name, value):
        #tag_id = ScienceTags.objects.filter(tag=value).first().id
        return queryset.filter(targettags__tag=value).distinct()

    class Meta:
        model = Target
        #fields = ['type', 'name', 'key', 'value', 'cone_search', 'targetlist__name']
        fields = ['name', 'cone_search', 'targetlist__name', 'sciencetags']
