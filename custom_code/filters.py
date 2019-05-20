from custom_code.models import TNSTarget
import django_filters

class TNSTargetFilter(django_filters.FilterSet):
    name = django_filters.CharFilter(field_name='name',lookup_expr='icontains')
    class Meta:
        model = TNSTarget
        fields = ['name']

    def __init__(self, *args, **kwargs):
        super(TNSTargetFilter, self).__init__(*args, **kwargs)
        if self.data == {}:
            self.queryset = self.queryset.none()
