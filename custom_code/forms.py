from tom_targets.forms import SiderealTargetCreateForm, TargetForm
from tom_targets.models import TargetExtra
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
