from django.db import models

# Create your models here.

class TNSTarget(models.Model):
    
    name = models.CharField(
        max_length=100, default='', verbose_name='Name', help_text='The name of the target, e.g. 2017cbv.'
    )
    name_prefix = models.CharField(
        max_length=100, default='', verbose_name='Name prefix', help_text='The name prefix, either AT (astronomical transient) or SN (supernova).',
        blank=True, null=True
    )
    ra = models.FloatField(
        verbose_name='Right Ascension', help_text='Right Ascension, in degrees.'
    )
    dec = models.FloatField(
        verbose_name='Declination', help_text='Declination, in degrees.'
    )
    redshift = models.FloatField(
        verbose_name='Redshift', help_text='Redshift.',
        blank=True, null=True
    )
    classification = models.CharField(
        max_length=100, default='', verbose_name='Target classification', help_text='The classification of this target, e.g. SN Ia.',
        blank=True, null=True
    )
    internal_name = models.CharField(
        max_length=100, default='', verbose_name='Internal name', help_text='Internal name for an object, e.g. DLT17u.',
        blank=True, null=True
    )
    source_group = models.CharField(
        max_length=100, default='', verbose_name='Source group', help_text='Source group, e.g. DLT',
        blank=True, null=True
    )
    lnd_jd = models.FloatField(
        verbose_name='Last non-detection JD', help_text='Last non-detection JD',
        blank=True, null=True
    )
    lnd_maglim = models.FloatField(
        verbose_name='Last non-detection limiting magnitude', help_text='Last non-detection limiting magnitude',
        blank=True, null=True
    )
    lnd_filter = models.CharField(
        max_length=100, default='', verbose_name='Last non-detection filter', help_text='Last non-detection filter',
        blank=True, null=True
    )
    disc_jd = models.FloatField(
        verbose_name='Discovery JD', help_text='Discovery JD',
        blank=True, null=True
    )
    disc_mag = models.FloatField(
        verbose_name='Discovery magnitude', help_text='Discovery magnitude',
        blank=True, null=True
    )
    disc_filter = models.CharField(
        max_length=100, default='', verbose_name='Discovery filter', help_text='Discovery filter',
        blank=True, null=True
    )
    all_phot = models.TextField(
        verbose_name='All photometry', help_text='All photometry',
        null=True, blank=True
    )
    TESS_sectors = models.CharField(
        max_length=255, default='', verbose_name='TESS Sectors', help_text='TESS sectors the object is in.',
        blank=True, null=True
    )

    class Meta:
        ordering = ('id',)
        get_latest_by = ('name',)
