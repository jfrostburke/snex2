# Generated by Django 3.2.16 on 2023-04-06 15:14

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tom_nonlocalizedevents', '0015_eventsequence_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='GWFollowupGalaxy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('catalog', models.CharField(blank=True, default='', help_text='Catalog corresponding to the Catalog ID', max_length=50, null=True)),
                ('catalog_objname', models.CharField(blank=True, default='', help_text='Name of this galaxy in the catalog', max_length=10, null=True)),
                ('ra', models.FloatField(help_text='Right Ascension, in degrees.', verbose_name='Right Ascension')),
                ('dec', models.FloatField(help_text='Declination, in degrees.', verbose_name='Declination')),
                ('dist', models.FloatField(blank=True, help_text='Distance in Mpc', null=True, verbose_name='Distance (Mpc)')),
                ('score', models.FloatField(default=0.0, help_text='Score of this galaxy for this EventLocalization', verbose_name='Score')),
                ('eventlocalization', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to='tom_nonlocalizedevents.eventlocalization')),
            ],
        ),
    ]
