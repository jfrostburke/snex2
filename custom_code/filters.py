from custom_code.models import TNSTarget
import django_filters
from django.db.models import Q
from astropy.time import Time
from datetime import datetime

class TNSTargetFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(field_name='name',lookup_expr='icontains')
    source_group = django_filters.CharFilter(field_name='source_group',lookup_expr='icontains')
    lnd_jd = django_filters.NumberFilter(field_name='lnd_jd', method='filter_lnd_jd')

    def filter_lnd_jd(self, queryset, name, value):
        jd_now = Time(datetime.utcnow()).jd
        return queryset.filter(
            Q(lnd_jd__gt=jd_now-float(value))
        )

    class Meta:
        model = TNSTarget
        fields = []
