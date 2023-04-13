from django.db import models
from tom_dataproducts.models import ReducedDatum
from tom_targets.models import Target
from django.contrib.auth.models import User

# Create your models here.

STATUS_CHOICES = (
    ('in prep', 'In Prep'),
    ('submitted', 'Submitted'),
    ('published', 'Published')
)

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
        ordering = ('-id',)
        get_latest_by = ('-name',)


class ReducedDatumExtra(models.Model):
    
    target = models.ForeignKey(
        Target, on_delete=models.CASCADE
    )
    data_type = models.CharField(
        max_length=100, default='', verbose_name='Data Type', 
        help_text='Type of data (either photometry or spectroscopy)'
    )
    key = models.CharField(
        max_length=200, default='', verbose_name='Key',
        help_text='Keyword for information being stored'
    )
    value = models.TextField(
        blank=True, default='', verbose_name='Value',
        help_text='String value of the information being stored'
    )
    float_value = models.FloatField(
        null=True, blank=True, verbose_name='Float Value',
        help_text='Float value of the information being stored, if applicable'
    )
    bool_value = models.BooleanField(
        null=True, blank=True, verbose_name='Boolean Value',
        help_text='Boolean value of the information being stored, if applicable'
    )

    class Meta:
        get_latest_by = ('id,')
        #unique_together = ['reduced_datum', 'key']

    def __str__(self):
        return f'{self.key}: {self.value}'

    def save(self, *args, **kwargs):
        try:
            self.float_value = float(self.value)
        except (TypeError, ValueError, OverflowError):
            self.float_value = None
        try:
            self.bool_value = bool(self.value)
        except (TypeError, ValueError, OverflowError):
            self.bool_value = None

        super().save(*args, **kwargs)


class ScienceTags(models.Model):

    tag = models.TextField(
        verbose_name='Science Tag', help_text='Science Tag', default=''
    )

    userid = models.CharField(
        max_length=100, default='', verbose_name='User ID', 
        help_text='ID of user who created this tag', blank=True, null=True
    )

    class Meta:
        get_latest_by = ('id',)

    def __str__(self):
        return self.tag


class TargetTags(models.Model):

    target = models.ForeignKey(
        Target, on_delete=models.CASCADE
    )

    tag = models.ForeignKey(
        ScienceTags, on_delete=models.CASCADE
    )


class Papers(models.Model):

    target = models.ForeignKey(
        Target, on_delete=models.CASCADE
    )

    author_first_name = models.CharField(
        max_length=20, default='', 
        verbose_name='First Author First Name', help_text='First name of the first author'
    )

    author_last_name = models.CharField(
        max_length=20, default='',
        verbose_name='First Author Last Name', help_text='Last name of the first author'
    )

    description = models.TextField(
        verbose_name='Description', help_text='Brief description of the contents of the paper', 
        default='', null=True
    )

    status = models.CharField(
        max_length=10, choices=STATUS_CHOICES
    )

    created = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.author_last_name} et al. ({self.status})'

    class Meta:
        get_latest_by = ('id',)


class InterestedPersons(models.Model):

    target = models.ForeignKey(
        Target, on_delete=models.CASCADE
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )


class BrokerTarget(models.Model):
    
    name = models.CharField(
        max_length=100, default='', verbose_name='Name', help_text='The internal name of the target'
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

    redshift_source = models.CharField(
        max_length=100, blank=True, null=True, verbose_name='Redshift Source', help_text='The source for this redshift, usually either TNS or Sherlock'
    )
    
    classification = models.CharField(
        max_length=100, default='', verbose_name='Target classification', help_text='The classification of this target, e.g. SN Ia.',
        blank=True, null=True
    )

    tns_target = models.ForeignKey(
        TNSTarget, blank=True, null=True, help_text='The TNS Target associated with this target, if one exists', on_delete=models.SET_NULL
    )

    stream_name = models.CharField(
        max_length=100, blank=True, default='', verbose_name='Stream Name', 
        help_text='Name of the stream that returned this target'
    )

    detections = models.TextField(
        verbose_name='All photometry', help_text='All photometry', null=True, blank=True
    )

    nondetections = models.TextField(
        verbose_name='All nondetections', help_text='All nondetections', null=True, blank=True
    )

    status = models.CharField(
        max_length=100, default='', verbose_name='Status', help_text='The status of this target'
    )

    created = models.DateTimeField(
        auto_now_add=True, verbose_name='Time Created',
        help_text='The time which this target was created in the TOM database.'
    )


class GladeCatalog(models.Model):

    pgc_no = models.IntegerField(
        verbose_name='PGC number', help_text='Principal Galaxies Catalog number',
        blank=True, null=True
    )

    gwgc_name = models.CharField(
        max_length=100, default='', blank=True, null=True, verbose_name='GWGC name',
        help_text='Name in the GWGC catalog'
    )

    hyperleda_name = models.CharField(
        max_length=100, default='', blank=True, null=True, verbose_name='HyperLEDA name',
        help_text='Name in the HyperLEDA catalog'
    )

    twomass_name = models.CharField(
        max_length=100, default='', blank=True, null=True, verbose_name='2MASS name',
        help_text='Name in the 2MASS XSC catalog'
    )

    wisexscos_name = models.CharField(
        max_length=100, default='', blank=True, null=True, verbose_name='WISExSCOS name',
        help_text='Name in the WISExSuperCOSMOS catalog'
    )

    sdss_dr16q_name = models.CharField(
        max_length=100, default='', blank=True, null=True, verbose_name='SDSS-DR16Q name',
        help_text='Name in the SDSS-DR16Q catalog'
    )

    object_type_flag = models.CharField(
        max_length=2, default='', blank=True, null=True, verbose_name='Object type flag',
        help_text='Q: source is from SDSS-DR16Q catalog; G: source is from another catalog and has not been identified as a quasar'
    )


    ra = models.FloatField(
        verbose_name='Right Ascension', help_text='Right Ascension, in degrees.'
    )
    
    dec = models.FloatField(
        verbose_name='Declination', help_text='Declination, in degrees.'
    )

    mag = models.JSONField(
        blank=True, null=True, verbose_name='Magnitudes', help_text='Magnitude information'
    )

    z_helio = models.FloatField(
        blank=True, null=True, help_text='Heliocentric redshift'
    )

    z_cmb = models.FloatField(
        blank=True, null=True, help_text='CMB-frame redshift'
    )

    z_flag = models.IntegerField(
        blank=True, null=True, help_text='0: CMB frame redshift and lum distance values are not corrected for peculiar velocity; 1: they are corrected values'
    )

    v_err = models.FloatField(
        blank=True, null=True, help_text='Error of redshift from peculiar velocity estimation'
    )

    z_err = models.FloatField(
        blank=True, null=True, help_text='Measurement error of heliocentric redshift'
    )

    d_l = models.FloatField(
        blank=True, null=True, verbose_name='luminosity distance', help_text='Luminosity distance, in Mpc'
    )

    d_l_err = models.FloatField(
        blank=True, null=True, verbose_name='luminosity distance err', help_text='Error in luminosity distance, in Mpc'
    )

    dist_flag = models.IntegerField(
        blank=True, null=True, verbose_name='distance flag', help_text='0: no measured redshift or distance; 1: distance from phot z; 2: redshift from lum dist; 3: distance from spec z'
    )

    m_star = models.FloatField(
        blank=True, null=True, help_text='Stellar mass, in 10^10 M_solar'
    )

    m_star_err = models.FloatField(
        blank=True, null=True, help_text='Absolute error of stellar mass, in 10^10 M_solar'
    )

    m_star_flag = models.IntegerField(
        blank=True, null=True, help_text='0: M_star calculated assuming no active star formation; 1: M_star calculated assuming active star formation'
    )

    merger_rate = models.FloatField(
        blank=True, null=True, help_text='Log10 of estimated BNS merger rate in galaxy, in Gyr^-1'
    )

    merger_rate_err = models.FloatField(
        blank=True, null=True, help_text='Absolute error of estimated BNS merger rate in galaxy'
    )


class NEDLVSCatalog(models.Model):

    name = models.CharField(
        max_length=100, default='', blank=True, null=True, verbose_name='Preferred NED name',
        help_text='Preferred object name in NED'
    )

    ra = models.FloatField(
        verbose_name='Right Ascension', help_text='Right Ascension, in degrees.'
    )
    
    dec = models.FloatField(
        verbose_name='Declination', help_text='Declination, in degrees.'
    )
    
    object_type = models.CharField(
        max_length=10, default='', blank=True, null=True, verbose_name='Object flag',
        help_text='Preferred object type in NED (see Table 1 in Cook et al.)'
    )

    z = models.FloatField(
        blank=True, null=True, help_text='Heliocentric redshift'
    )
    
    z_err = models.FloatField(
        blank=True, null=True, help_text='Measurement error of heliocentric redshift'
    )

    z_tech = models.CharField(
        max_length=10, default='', blank=True, null=True, 
        help_text='Technique used to measure redshift (SPEC, PHOT, UNKN, INFD, MOD, None or NULL)'
    )

    z_qual = models.BooleanField(
        null=True, blank=True, default=False, verbose_name='Redshift qualifier',
        help_text='Qualifier flag indicating reliability of redshift (True=unreliable)'
    )

    z_qual_flag = models.BooleanField(
        null=True, blank=True, default=False, verbose_name='Redshift qualifier flag',
        help_text='Boolean flag indicating that the zqual flag has been updated in NED-LVS'
    )

    z_refcode = models.CharField(
        max_length=20, default='', blank=True, null=True,
        help_text='Reference code for the publication that provided the redshift'
    )

    z_dist = models.FloatField(
        blank=True, null=True, help_text='Redshift-independent luminosity distance computed as the weighted average of measurements in either the primary or secondary indicators'
    )

    z_dist_err = models.FloatField(
        blank=True, null=True, help_text='Uncertainty in z_dist'
    )

    z_dist_method = models.CharField(
        max_length=31, default='', blank=True, null=True,
        help_text='Method used to measure the redshift-independent distance when a single method is used to compute the weighted average, otherwise "Wavg" when a mixture of methods are used (Cepheid, SNIa, TRGB, Wavg, etc.)'
    )

    z_dist_indicator = models.CharField(
        max_length=20, default='', blank=True, null=True,
        help_text='Measurement type indicator for redshift-independent distance (Primary or Secondary)'
    )

    z_dist_refcode = models.CharField(
        max_length=20, default='', blank=True, null=True,
        help_text='Reference code for the publication that provided the distance when a single measurement was chosen, otherwise "Mix" indicates an average of multiple measurements was used (refcode or Mix)'
    )

    d_l = models.FloatField(
        blank=True, null=True, verbose_name='luminosity distance', 
        help_text='Luminosity distance, in Mpc'
    )

    d_l_err = models.FloatField(
        blank=True, null=True, verbose_name='luminosity distance err', 
        help_text='Error in luminosity distance, in Mpc'
    )

    dist_method = models.CharField(
        max_length=31, default='', blank=True, null=True, 
        help_text='Method used in the selected distance (Redshift or zIndependent)'
    )

    ebv = models.FloatField(
        blank=True, null=True, verbose_name='E(B-V)',
        help_text='Foreground MW reddening E(B-V) from Schlafly & Finkbeiner (2011)'
    )

    extinction = models.JSONField(
        blank=True, null=True, verbose_name='Extinctions', 
        help_text='MW extinctions assuming Fitzpatrick et al. (1999)'
    )
    
    mag = models.JSONField(
        blank=True, null=True, verbose_name='Magnitudes', help_text='Apparent magnitudes'
    )

    lum = models.JSONField(
        blank=True, null=True, verbose_name='Luminosities', help_text='Monochromatic luminosities'
    )

    galex_phot = models.CharField(
        max_length=10, default='', blank=True, null=True,
        help_text='Flag indicating which catalog was used for GALEX photometry (ASC, MSC, z0MGS)'
    )

    tmass_phot = models.CharField(
        max_length=10, default='', blank=True, null=True,
        help_text='Flag indicating which catalog was used for 2MASS photometry (PSC, XSC, LGA)'
    )
    
    wise_phot = models.CharField(
        max_length=10, default='', blank=True, null=True,
        help_text='Flag indicating which catalog was used for WISE photometry (Pfit, APER, z0MGS)'
    ) 
    
    sfr = models.JSONField(
        blank=True, null=True, verbose_name='Star Formation Rates', help_text='Star formation rate using either W4 luminosity scaling relation, or  FUV+W4 luminosity scaling relation (Section 2.4 of Cook et al.)'
    )

    et_flag = models.BooleanField(
        blank=True, null=True, default=False,
        help_text='Boolean flag indicating an object is an early-type galaxy determined via IR or UV-IR colors (Section 4.3 of Cook et al.; True=colors indicate an early-type galaxy), and that the SFRs may be overestimated to varying degrees.'
    )

    m_star = models.FloatField(
        blank=True, null=True, help_text='Stellar mass using a W1 luminosity scaling relationship (Section 2.4 of Cook et al.)'
    )

    m_star_err = models.FloatField(
        blank=True, null=True, help_text='Uncertainty in m_star'
    )

    ml_ratio = models.FloatField(
        blank=True, null=True, 
        help_text='The mass-to-light ratio used to calculate m_star (Section 2.4 of Cook et al.)'
    )


class TimeUsed(models.Model):
    semester_name = models.TextField(
        verbose_name='Semester Name', help_text='Name of the semester', null=False, blank=False
    )

    telescope_class = models.TextField(
        verbose_name='Telescope Class', help_text='Class of telescope (1M or 2M)'
    )

    std_time_used = models.FloatField(
        verbose_name='Standard Time Used', help_text='Hours of standard time that have been used', default=0.0, blank=True
    )

    std_time_allocated = models.FloatField(
        verbose_name='Standard Time Allocated', help_text='Hours of standard time allocated for this semester', default=0.0, blank=True
    )
    
    tc_time_used = models.FloatField(
        verbose_name='Time Critical Time Used', help_text='Hours of Time Critical time that have been used', default=0.0, blank=True
    )

    tc_time_allocated = models.FloatField(
        verbose_name='Time Critical Time Allocated', help_text='Hours of Time Critical time allocated for this semester', default=0.0, blank=True
    )

    rr_time_used = models.FloatField(
        verbose_name='Rapid Response Time Used', help_text='Hours of Rapid Response time that have been used', default=0.0, blank=True
    )

    rr_time_allocated = models.FloatField(
        verbose_name='Rapid Response Time Allocated', help_text='Hours of Rapid Response time allocated for this semester', default=0.0, blank=True
    )

    frac_of_semester = models.FloatField(
        verbose_name='Fraction of Semester', help_text='Fraction of this semester completed', default=0.0, blank=True
    )

    class Meta:
        unique_together = ['semester_name', 'telescope_class']
