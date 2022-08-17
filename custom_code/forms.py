from tom_targets.forms import SiderealTargetCreateForm, TargetForm
from tom_targets.models import Target, TargetExtra
from tom_dataproducts.forms import DataProductUploadForm
from tom_observations.widgets import FilterField
from tom_dataproducts.models import DataProduct
from guardian.shortcuts import assign_perm, get_groups_with_perms, remove_perm
from django import forms
from custom_code.models import ScienceTags, TargetTags, Papers
from django.conf import settings
from django.db.models.functions import Lower
from django.core.exceptions import ValidationError
from django.contrib.auth.models import Group

class CustomTargetCreateForm(SiderealTargetCreateForm):

    sciencetags = forms.ModelMultipleChoiceField(ScienceTags.objects.all().order_by(Lower('tag')), widget=forms.CheckboxSelectMultiple, label='Science Tags', required=False)

    def clean(self):
        cleaned_data = super().clean()
        self.cleaned_data = cleaned_data


    def save(self, commit=True):
        instance = super().save(commit=commit)
        if commit:
            #for field in settings.EXTRA_FIELDS:
            #    if self.cleaned_data.get(field['name']) is not None:
            #        print(instance.id, field['name'])
            #        TargetExtra.objects.update_or_create(
            #                target=instance,
            #                key=field['name'],
            #                defaults={'value': self.cleaned_data[field['name']]}
            #        )
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
        choices = [('LCO', 'LCO'), ('UC Davis', 'UC Davis'), ('Arizona', 'Arizona')]
        help_text="Or add another group"
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


class InstrumentWidget(forms.widgets.MultiWidget):
    def __init__(self, attrs=None):
        choices = [('LCO', 'LCO'), ('Swift', 'Swift'), ('Gaia', 'Gaia'), ('TESS', 'TESS')]
        help_text="Or add another instrument"
        widget = (forms.widgets.RadioSelect(choices=choices),
                  forms.widgets.TextInput(attrs={'placeholder': help_text})
                )
        super(InstrumentWidget, self).__init__(widget, attrs=attrs)

    def decompress(self, value):
        if value:
            if value in [x[0] for x in self.choices]:
                return [value, ""]
            else:
                return ["", value]
        else:
            return ["", ""]


class TemplateSourceWidget(forms.widgets.MultiWidget):
    def __init__(self, attrs=None):
        choices = [('LCO', 'LCO'), ('SDSS', 'SDSS')]
        help_text="Other"
        widget = (forms.widgets.RadioSelect(choices=choices),
                  forms.widgets.TextInput(attrs={'placeholder': help_text})
                )
        super(TemplateSourceWidget, self).__init__(widget, attrs=attrs)

    def decompress(self, value):
        if value:
            if value in [x[0] for x in self.choices]:
                return [value, ""]
            else:
                return ["", value]
        else:
            return ["", ""]


class MultiField(forms.MultiValueField):

    def __init__(self, required=False, widget=None, label=None, initial=None, help_text=None, choices=None):
        field = (forms.ChoiceField(choices=choices, required=False), forms.CharField(required=False))
        super(MultiField, self).__init__(required=False, fields=field, widget=widget, label=label, initial=initial, help_text=help_text)


    def compress(self, data_list):
        if not data_list:
            raise ValidationError('Select choice or enter text for this field')
        return data_list[0] or data_list[1]


class CustomDataProductUploadForm(DataProductUploadForm):
    photometry_type = forms.ChoiceField(
        choices=[('Aperture', 'Aperture'), 
                 ('PSF', 'PSF'),
                 ('Mixed', 'Mixed')
        ],
        widget=forms.RadioSelect(),
        required=False
    )

    instrument = MultiField(
        choices=[('LCO', 'LCO'), 
                 ('Swift', 'Swift'), 
                 ('Gaia', 'Gaia'),
                 ('Tess', 'Tess')
        ],
        widget=InstrumentWidget,
        help_text="Or add another instrument"
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

    #template_source = MultiField(
    template_source = forms.ChoiceField(
        choices=[('LCO', 'LCO'),
                 ('SDSS', 'SDSS'),
                 ('PS1', 'PS1'),
        ],
        #widget=TemplateSourceWidget,
        widget=forms.RadioSelect(),
        required=False
    )

    reducer_group = MultiField(
        choices=[('LCO', 'LCO'),
                 ('UC Davis', 'UC Davis'),
                 ('U of A', 'U of A')
        ],
        help_text="Or add another group",
        widget=ReducerGroupWidget
    )

    #used_in = forms.ChoiceField(
    #    choices=[('', '')],
    #    required=False
    #)
    used_in = forms.ModelChoiceField(
        queryset=Papers.objects.all(),
        required=False
    )

    final_reduction = forms.BooleanField(
        required=False
    )

    def __init__(self, *args, **kwargs):
        super(CustomDataProductUploadForm, self).__init__(*args, **kwargs)
        initial_args = kwargs.get('initial', '')
        if initial_args:
            target = initial_args.get('target', '')
            self.fields['used_in'] = forms.ModelChoiceField(queryset=Papers.objects.filter(target=target), required=False)


class PapersForm(forms.ModelForm):

    class Meta:
        model = Papers
        fields = ['target', 'author_first_name', 'author_last_name', 'status', 'description']
        labels = {
            'author_first_name': '',
            'author_last_name': '',
            'status': '',
            'description': ''
        }
        help_texts = {
            'author_first_name': '',
            'author_last_name': '',
            'status': '',
            'description': ''
        }
        widgets = {
            'target': forms.HiddenInput(),
            'author_first_name': forms.Textarea(
                attrs={
                    'placeholder': 'First name of first author',
                    'rows': 1,
                    'cols': 20
                }
            ),
            'author_last_name': forms.Textarea(
                attrs={
                    'placeholder': 'Last name of first author',
                    'rows': 1,
                    'cols': 20
                }
            ),
            'description': forms.Textarea(
                attrs={
                    'placeholder': 'Brief description of contents of this paper, i.e. "All photometry and spectra"',
                    'rows': 5,
                    'cols': 20
                }
            )
        }


class PhotSchedulingForm(forms.Form):

    name = forms.CharField(widget=forms.HiddenInput())
    observation_id = forms.IntegerField(widget=forms.HiddenInput())
    target_id = forms.IntegerField(widget=forms.HiddenInput())
    facility = forms.CharField(widget=forms.HiddenInput())
    observation_type = forms.CharField(widget=forms.HiddenInput())
    cadence_strategy = forms.CharField(widget=forms.HiddenInput(), required=False)
    observing_parameters = forms.CharField(max_length=1024, widget=forms.HiddenInput()) 
    
    cadence_frequency = forms.FloatField(min_value=0.0, label='')
    ipp_value = forms.FloatField(min_value=0.5, max_value=2.0, label='')
    max_airmass = forms.FloatField(min_value=0.0, label='')
    reminder = forms.FloatField(min_value=0.0, label='')
    filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
    delay_start = forms.FloatField(min_value=0.0, initial=0.0, label='')
    
    def __init__(self, *args, **kwargs):
        super(PhotSchedulingForm, self).__init__(*args, **kwargs)
        for f in self.filters:
            if f in kwargs.get('initial', ''):
                self.fields[f] = FilterField(label=f[0], required=False)

        self.fields['cadence_frequency'].widget.attrs['class'] = 'cadence-input'
        self.fields['delay_start'].widget.attrs['class'] = 'delay-start-input'


class SpecSchedulingForm(forms.Form):

    name = forms.CharField(widget=forms.HiddenInput())
    observation_id = forms.IntegerField(widget=forms.HiddenInput())
    target_id = forms.IntegerField(widget=forms.HiddenInput())
    facility = forms.CharField(widget=forms.HiddenInput())
    observation_type = forms.CharField(widget=forms.HiddenInput())
    cadence_strategy = forms.CharField(widget=forms.HiddenInput(), required=False)
    observing_parameters = forms.CharField(max_length=1024, widget=forms.HiddenInput()) 
    
    cadence_frequency = forms.FloatField(min_value=0.0, label='')
    ipp_value = forms.FloatField(min_value=0.5, max_value=2.0, label='')
    max_airmass = forms.FloatField(min_value=0.0, label='')
    reminder = forms.FloatField(min_value=0.0, label='')
    exposure_time = forms.IntegerField(min_value=1, label='')
    delay_start = forms.FloatField(min_value=0.0, initial=0.0, label='')
    
    def __init__(self, *args, **kwargs):
        super(SpecSchedulingForm, self).__init__(*args, **kwargs)
        self.fields['cadence_frequency'].widget.attrs['class'] = 'cadence-input'
        self.fields['delay_start'].widget.attrs['class'] = 'delay-start-input'


class ReferenceStatusForm(forms.Form):

    status = forms.ChoiceField(
        choices=[('Required', 'Required'),
                 ('Undetermined', 'Undetermined'),
                 ('Not Necessary', 'Not Necessary'),
                 ('Obtained', 'Obtained')
        ],
        widget=forms.RadioSelect(),
        label=''
    )

    target = forms.IntegerField(widget=forms.HiddenInput())

    #target = forms.ModelChoiceField(queryset=Target.objects.none(),
    #                                widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super(ReferenceStatusForm, self).__init__(*args, **kwargs)


class ThumbnailForm(forms.Form):

    filenames = forms.ChoiceField(choices=[('','')], widget=forms.Select(), label='Filename')
    zoom = forms.FloatField(min_value=0.1, max_value=10.0, label='Zoom')
    sigma = forms.FloatField(min_value=1.0, max_value=50.0, label='Sigma')

    def __init__(self, *args, **kwargs):
        filename_choices = kwargs.pop('choices')['filenames']
        super(ThumbnailForm, self).__init__(*args, **kwargs)
        self.fields['filenames'].choices = filename_choices
