from django.db import models
from tom_nonlocalizedevents.models import EventLocalization

# Create your models here.

class GWFollowupGalaxy(models.Model):
    catalog = models.CharField(
        max_length=50, default='', blank=True, null=True,
        help_text='Catalog corresponding to the Catalog ID'
    )

    catalog_objname = models.CharField(
        max_length=50, default='', blank=True, null=True,
        help_text='Name of this galaxy in the catalog'
    )

    ra = models.FloatField(
        verbose_name='Right Ascension', help_text='Right Ascension, in degrees.'
    )

    dec = models.FloatField(
        verbose_name='Declination', help_text='Declination, in degrees.'
    )

    dist = models.FloatField(
        verbose_name='Distance (Mpc)', help_text='Distance in Mpc',
        blank=True, null=True
    )

    score = models.FloatField(
        verbose_name='Score', help_text='Score of this galaxy for this EventLocalization',
        default=0.0
    )

    eventlocalization = models.ForeignKey(
        EventLocalization, on_delete=models.CASCADE
    )

