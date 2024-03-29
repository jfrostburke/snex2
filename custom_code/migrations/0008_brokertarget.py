# Generated by Django 3.1.5 on 2022-04-05 00:16

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('custom_code', '0007_interestedpersons'),
    ]

    operations = [
        migrations.CreateModel(
            name='BrokerTarget',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(default='', help_text='The internal name of the target', max_length=100, verbose_name='Name')),
                ('ra', models.FloatField(help_text='Right Ascension, in degrees.', verbose_name='Right Ascension')),
                ('dec', models.FloatField(help_text='Declination, in degrees.', verbose_name='Declination')),
                ('redshift', models.FloatField(blank=True, help_text='Redshift.', null=True, verbose_name='Redshift')),
                ('redshift_source', models.CharField(blank=True, help_text='The source for this redshift, usually either TNS or Sherlock', max_length=100, null=True, verbose_name='Redshift Source')),
                ('classification', models.CharField(blank=True, default='', help_text='The classification of this target, e.g. SN Ia.', max_length=100, null=True, verbose_name='Target classification')),
                ('stream_name', models.CharField(blank=True, default='', help_text='Name of the stream that returned this target', max_length=100, verbose_name='Stream Name')),
                ('detections', models.TextField(blank=True, help_text='All photometry', null=True, verbose_name='All photometry')),
                ('nondetections', models.TextField(blank=True, help_text='All nondetections', null=True, verbose_name='All nondetections')),
                ('status', models.CharField(default='', help_text='The status of this target', max_length=100, verbose_name='Status')),
                ('tns_target', models.ForeignKey(blank=True, help_text='The TNS Target associated with this target, if one exists', null=True, on_delete=django.db.models.deletion.SET_NULL, to='custom_code.tnstarget')),
            ],
        ),
    ]
