# Generated by Django 3.2.16 on 2022-12-08 17:43

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('custom_code', '0009_brokertarget_created'),
    ]

    operations = [
        migrations.CreateModel(
            name='TimeUsed',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('semester_name', models.TextField(help_text='Name of the semester', verbose_name='Semester Name')),
                ('telescope_class', models.TextField(help_text='Class of telescope (1M or 2M)', verbose_name='Telescope Class')),
                ('std_time_used', models.FloatField(blank=True, default=0.0, help_text='Hours of standard time that have been used', verbose_name='Standard Time Used')),
                ('std_time_allocated', models.FloatField(blank=True, default=0.0, help_text='Hours of standard time allocated for this semester', verbose_name='Standard Time Allocated')),
                ('tc_time_used', models.FloatField(blank=True, default=0.0, help_text='Hours of Time Critical time that have been used', verbose_name='Time Critical Time Used')),
                ('tc_time_allocated', models.FloatField(blank=True, default=0.0, help_text='Hours of Time Critical time allocated for this semester', verbose_name='Time Critical Time Allocated')),
                ('rr_time_used', models.FloatField(blank=True, default=0.0, help_text='Hours of Rapid Response time that have been used', verbose_name='Rapid Response Time Used')),
                ('rr_time_allocated', models.FloatField(blank=True, default=0.0, help_text='Hours of Rapid Response time allocated for this semester', verbose_name='Rapid Response Time Allocated')),
                ('frac_of_semester', models.FloatField(blank=True, default=0.0, help_text='Fraction of this semester completed', verbose_name='Fraction of Semester')),
            ],
            options={
                'unique_together': {('semester_name', 'telescope_class')},
            },
        ),
    ]