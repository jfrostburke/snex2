from tom_targets.forms import SiderealTargetCreateForm, TargetForm
from tom_targets.models import TargetExtra
from tom_dataproducts.forms import DataProductUploadForm
from tom_dataproducts.models import DataProduct
from guardian.shortcuts import assign_perm, get_groups_with_perms, remove_perm
from django import forms
from custom_code.models import ScienceTags, TargetTags
from django.conf import settings
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group
class CustomTargetCreateForm(SiderealTargetCreateForm):

    sciencetags = forms.ModelMultipleChoiceField(ScienceTags.objects.all().order_by(Lower('tag')), required=False, widget=forms.CheckboxSelectMultiple)

    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            for field in settings.EXTRA_FIELDS:
                if self.cleaned_data.get(field['name']) is not None:
                    TargetExtra.objects.update_or_create(
                            target=instance,
                            key=field['name'],
                            defaults={'value': self.cleaned_data[field['name']]}
                    )
            # Save groups for this target
            for group in self.cleaned_data['groups']:
                assign_perm('tom_targets.view_target', group, instance)
                assign_perm('tom_targets.change_target', group, instance)
                assign_perm('tom_targets.delete_target', group, instance)
            for group in get_groups_with_perms(instance):
                if group not in self.cleaned_data['groups']:
                    remove_perm('tom_targets.view_target', group, instance)
                    remove_perm('tom_targets.change_target', group, instance)
                    remove_perm('tom_targets.delete_target', group, instance)

            # Save science tags for this target
            for tag in self.cleaned_data['sciencetags']:
                TargetTags.objects.update_or_create(
                        target=instance,
                        tag=tag
                )

        return instance


#class DataProductUpdateForm(forms.ModelForm):
#
#    class Meta:
#        model=DataProduct
#        fields = '__all__'
#
#    groups = forms.ModelMultipleChoiceField(Group.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)


class ReducerGroupWidget(forms.widgets.MultiWidget):
    def __init__(self, attrs=None):
        choices = [('LCO', 'LCO'), ('UC Davis', 'UC Davis'), ('UofA', 'UofA')]
        help_text="Or add your own group"
        widget = (forms.widgets.RadioSelect(choices=choices),
                  forms.widgets.TextInput(attrs={'placeholder': help_text})
                )
        super(ReducerGroupWidget, self).__init__(widget, attrs=attrs)

    def decompress(self, value):
        if value:
            if value in [x[0] for x in self.choices]:
                return [value, ""]
            else:
                return ["", value]
        else:
            return ["", ""]


class ReducerGroupField(forms.MultiValueField):
    widget = ReducerGroupWidget

    def __init__(self, required=False, widget=None, label=None, initial=None, help_text=None, choices=None):
        #choices = kwargs.pop("choices",[])
        field = (forms.ChoiceField(choices=choices, required=False), forms.CharField(required=False))
        super(ReducerGroupField, self).__init__(required=False, fields=field, widget=widget, label=label, initial=initial, help_text=help_text)

    #def __init__(self, choices, *args, **kwargs):
    #    fields = (forms.ChoiceField(choices=choices, required=False), forms.CharField(required=False))
    #    self.widget = ReducerGroupWidget(widgets=[f.widget for f in fields])
    #    super(ReducerGroupField, self).__init__(required=False, fields=fields, *args, **kwargs)

    def compress(self, data_list):
        if not data_list:
            raise ValidationError('Select choice or enter text for this field')
        return data_list[0] or data_list[1]


class CustomDataProductUploadForm(DataProductUploadForm):
    photometry_type = forms.ChoiceField(
        choices=[('Aperture', 'Aperture'), 
                 ('PSF', 'PSF')
        ],
        widget=forms.RadioSelect(),
        required=False
    )

    instrument = forms.ChoiceField(
        choices=[('LCO', 'LCO'), 
                 ('Swift', 'Swift'), 
                 ('Gaia', 'Gaia'),
                 ('Tess', 'Tess')
        ],
        widget=forms.RadioSelect(),
        required=False
    )

    background_subtracted = forms.BooleanField(
        required=False
    )

    subtraction_algorithm = forms.ChoiceField(
        choices=[('Hotpants', 'Hotpants'),
                 ('PyZOGY', 'PyZOGY')
        ],
        widget=forms.RadioSelect(),
        required=False
    )

    template_source = forms.ChoiceField(
        choices=[('LCO', 'LCO'),
                 ('SDSS', 'SDSS'),
                 ('other', 'other')
        ],
        widget=forms.RadioSelect(),
        required=False
    )

    reducer_group = ReducerGroupField(
    #reducer_group = forms.ChoiceField(
        choices=[('LCO', 'LCO'),
                 ('UC Davis', 'UC Davis'),
                 ('U of A', 'U of A')
        ],
        help_text="Or add your own group",
        #required=False
    )

    used_in = forms.ChoiceField(
        choices=[('Papers go here', 'Papers go here')],
        required=False
    )

    final_reduction = forms.BooleanField(
        required=False
    )
