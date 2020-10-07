from tom_targets.forms import SiderealTargetCreateForm, TargetForm
from tom_targets.models import TargetExtra
from tom_dataproducts.forms import DataProductUploadForm
from guardian.shortcuts import assign_perm, get_groups_with_perms, remove_perm
from django import forms
from custom_code.models import ScienceTags, TargetTags
from django.conf import settings
from django.db.models.functions import Lower

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


class ReducerGroupWidget(forms.widgets.MultiWidget):
    def __init__(self, attrs=None):
        choices = [('LCO', 'LCO'), ('UC Davis', 'UC Davis'), ('UofA', 'UofA')]
        help_text="Add your own group"
        widget = (forms.widgets.RadioSelect(choices=choices),
                  forms.widgets.TextInput(attrs={'placeholder': help_text})
                )
        super(ReducerGroupWidget, self).__init__(widget, attrs=attrs)

    def decompress(self, value):
        if value:
            if value.text_val:
                return [value.text_val]
            elif value.choice_val:
                return [value.choice_val]
        return [None]


class ReducerGroupField(forms.MultiValueField):
    widget = ReducerGroupWidget

    def __init__(self, required=False, widget=None, label=None, initial=None, help_text=None, choices=None):
        #choices = kwargs.pop("choices",[])
        field = (forms.ChoiceField(choices=choices), forms.CharField())
        super(ReducerGroupField, self).__init__(fields=field, widget=widget, label=label, initial=initial, help_text=help_text)


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

    reducer_group = ReducerGroupField(#forms.ChoiceField(
        choices=[('LCO', 'LCO'),
                 ('UC Davis', 'UC Davis'),
                 ('U of A', 'U of A')
        ],
        required=False
    )

    used_in = forms.ChoiceField(
        choices=[('Papers go here', 'Papers go here')],
        required=False
    )

    final_reduction = forms.BooleanField(
        required=False
    )
