from django_filters.views import FilterView
from django.shortcuts import redirect, render
from django.db import transaction, IntegrityError
from django.db.models import Q, DateTimeField, FloatField, F, ExpressionWrapper
from django.db.models.functions import Cast
from django.http import HttpResponse, JsonResponse, HttpResponseRedirect
from django.views.generic import View
from django.views.generic.list import ListView
from django.views.generic.edit import FormView, UpdateView
from django.views.generic.detail import DetailView
from django.urls import reverse
from django.template.loader import render_to_string
from django_comments.models import Comment
from django_comments.signals import comment_was_posted
from django.dispatch import receiver

from custom_code.models import TNSTarget, ScienceTags, TargetTags, ReducedDatumExtra, Papers, InterestedPersons
from custom_code.filters import TNSTargetFilter, CustomTargetFilter#, BrokerTargetFilter
from tom_targets.models import TargetList, Target, TargetExtra, TargetName
from tom_targets.templatetags.targets_extras import target_extra_field
from guardian.mixins import PermissionListMixin
from guardian.models import GroupObjectPermission
from guardian.shortcuts import get_objects_for_user, assign_perm, remove_perm, get_users_with_perms
from django.contrib.auth.models import User, Group
from django.contrib.contenttypes.models import ContentType
from django.contrib import messages
from django.conf import settings
from django.contrib.postgres.fields.jsonb import KeyTextTransform

import os
from urllib.parse import urlencode
from astropy.coordinates import SkyCoord
from astropy import units as u
from astropy.time import Time
from datetime import datetime, date, timedelta
import json
from statistics import median
from collections import OrderedDict

from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from contextlib import contextmanager
from plotly import offline
import plotly.graph_objs as go
from tom_dataproducts.models import ReducedDatum
from django.utils.safestring import mark_safe
from custom_code.templatetags.custom_code_tags import get_24hr_airmass, airmass_collapse, lightcurve_collapse, spectra_collapse, lightcurve_fits, lightcurve_with_extras, get_best_name, dash_spectra_page, scheduling_list_with_form
from custom_code.hooks import _get_tns_params, _return_session
from custom_code.thumbnails import make_thumb

from .forms import CustomTargetCreateForm, CustomDataProductUploadForm, PapersForm, PhotSchedulingForm, ReferenceStatusForm
from tom_targets.views import TargetCreateView
from tom_common.hooks import run_hook
from tom_dataproducts.views import DataProductUploadView, DataProductDeleteView
from tom_dataproducts.models import DataProduct
from tom_dataproducts.exceptions import InvalidFileFormatException
from custom_code.processors.data_processor import run_custom_data_processor
from guardian.shortcuts import assign_perm

from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from tom_observations.facility import get_service_class
from tom_observations.cadence import get_cadence_strategy
from tom_observations.facilities.lco import FAILED_OBSERVING_STATES, TERMINAL_OBSERVING_STATES
from tom_observations.views import ObservationCreateView, ObservationListView, ObservationRecordCancelView
import requests
from rest_framework.authtoken.models import Token
import base64

import logging

logger = logging.getLogger(__name__)

# Create your views here.

def make_coords(ra, dec):
    coords = SkyCoord(ra, dec, unit=u.deg)
    coords = coords.to_string('hmsdms',sep=':',precision=1,alwayssign=True)
    return coords

def make_lnd(mag, filt, jd, jd_now):
    if not jd:
        return 'Archival'
    diff = jd_now - jd
    lnd = '{mag:.2f} ({filt}: {time:.2f})'.format(
        mag = mag,
        filt = filt,
        time = diff)
    return lnd

def make_magrecent(all_phot, jd_now):
    all_phot = json.loads(all_phot)
    jds = [all_phot[obs]['jd'] for obs in all_phot]
    if not jds:
        return 'None'
    recent_jd = max(jds)
    recent_phot = [all_phot[obs] for obs in all_phot if
        all_phot[obs]['jd'] == recent_jd][0]
    mag = float(recent_phot['flux'])
    filt = recent_phot['filters']['name']
    diff = jd_now - float(recent_jd)
    mag_recent = '{mag:.2f} ({filt}: {time:.2f})'.format(
        mag = mag,
        filt = filt,
        time = diff)
    return mag_recent

class TNSTargets(FilterView):

    # Look at https://simpleisbetterthancomplex.com/tutorial/2016/11/28/how-to-filter-querysets-dynamically.html
    
    template_name = 'custom_code/tns_targets.html'
    model = TNSTarget
    paginate_by = 10
    context_object_name = 'tnstargets'
    strict = False
    filterset_class = TNSTargetFilter

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        jd_now = Time(datetime.utcnow()).jd
        TNS_URL = "https://www.wis-tns.org/object/"
        for target in context['object_list']:
            logger.info('Getting context data for TNS Target %s', target)
            target.coords = make_coords(target.ra, target.dec)
            target.mag_lnd = make_lnd(target.lnd_maglim,
                target.lnd_filter, target.lnd_jd, jd_now)
            target.mag_recent = make_magrecent(target.all_phot, jd_now)
            target.link = TNS_URL + target.name
        return context

class TargetListView(PermissionListMixin, FilterView):
    """
    View for listing targets in the TOM. Only shows targets that the user is authorized to view.     Requires authorization.
    """
    template_name = 'tom_targets/target_list.html'
    paginate_by = 25
    strict = False
    model = Target
    filterset_class = CustomTargetFilter
    permission_required = 'tom_targets.view_target'
    ordering = ['-id']

    def get_context_data(self, *args, **kwargs):
        """
        Adds the number of targets visible, the available ``TargetList`` objects if the user is a    uthenticated, and
        the query string to the context object.

        :returns: context dictionary
        :rtype: dict
        """
        context = super().get_context_data(*args, **kwargs)
        context['target_count'] = context['paginator'].count
        # hide target grouping list if user not logged in
        context['groupings'] = (TargetList.objects.all()
                                if self.request.user.is_authenticated
                                else TargetList.objects.none())
        context['query_string'] = self.request.META['QUERY_STRING']
        return context

def target_redirect_view(request):
 
    search_entry = request.GET['name'] 
    logger.info('Redirecting search for %s', search_entry)
    
    target_search_coords = None
    for i in [',', ' ']:
        if i in search_entry:
            target_search_coords = search_entry.split(i)
            break 

    if target_search_coords is not None:
        ra = target_search_coords[0]
        dec = target_search_coords[1]
        radius = 1

        if ':' in ra and ':' in dec:
            ra_hms = ra.split(':')
            ra_hour = float(ra_hms[0])
            ra_min = float(ra_hms[1])
            ra_sec = float(ra_hms[2])

            dec_dms = dec.split(':')
            dec_deg = float(dec_dms[0])
            dec_min = float(dec_dms[1])
            dec_sec = float(dec_dms[2])

            # Convert to degree
            ra = (ra_hour*15) + (ra_min*15/60) + (ra_sec*15/3600)
            if dec_deg > 0:
                dec = dec_deg + (dec_min/60) + (dec_sec/3600)
            else:
                dec = dec_deg - (dec_min/60) - (dec_sec/3600)

        else:
            ra = float(ra)
            dec = float(dec)

        target_match_list = Target.objects.filter(ra__gte=ra-1, ra__lte=ra+1, dec__gte=dec-1, dec__lte=dec+1)

        if len(target_match_list) == 1:
            target_id = target_match_list[0].id
            return(redirect('/targets/{}/'.format(target_id)))
        
        else:
            return(redirect('/targets/?cone_search={ra}%2C{dec}%2C1'.format(ra=ra,dec=dec)))

    else:
        target_match_list = Target.objects.filter(Q(name__icontains=search_entry) | Q(aliases__name__icontains=search_entry)).distinct()

        if len(target_match_list) == 1:
            target_id = target_match_list[0].id
            return(redirect('/targets/{}/'.format(target_id)))

        else: 
            return(redirect('/targets/?name={}'.format(search_entry)))


def add_tag_view(request):
    new_tag = request.GET.get('new_tag', None)
    username = request.user.username
    tag, _ = ScienceTags.objects.get_or_create(tag=new_tag, userid=username)
    response_data = {'success': 1}
    return HttpResponse(json.dumps(response_data), content_type='application/json')


def save_target_tag_view(request):
    tag_names = json.loads(request.GET.get('tags', None))
    target_id = request.GET.get('targetid', None)
    TargetTags.objects.all().filter(target_id=target_id).delete()
    for i in range(len(tag_names)):
        tag_id = ScienceTags.objects.filter(tag=tag_names[i]).first().id
        target_tag, _ = TargetTags.objects.get_or_create(tag_id=tag_id, target_id=target_id)
    response_data = {'success': 1}
    return HttpResponse(json.dumps(response_data), content_type='application/json')


def targetlist_collapse_view(request):

    target_id = request.GET.get('target_id', None)
    logger.info('Getting plots for target %s', target_id)
    target = Target.objects.get(id=target_id)
    user_id = request.GET.get('user_id', None)
    user = User.objects.get(id=user_id)

    lightcurve_plot = lightcurve_collapse(target, user)['plot']
    spectra_plot = spectra_collapse(target)['plot']
    airmass_plot = airmass_collapse(target)['figure']

    context = {
        'lightcurve_plot': lightcurve_plot,
        'spectra_plot': spectra_plot,
        'airmass_plot': airmass_plot
    }

    return HttpResponse(json.dumps(context), content_type='application/json')

class CustomTargetCreateView(TargetCreateView):

    def get_form_class(self):
        return CustomTargetCreateForm

    def get_initial(self):
        return {
            'type': self.get_target_type(),
            'groups': Group.objects.filter(name__in=settings.DEFAULT_GROUPS),
            **dict(self.request.GET.items())
        }

    def get_context_data(self, **kwargs):
        context = super(CustomTargetCreateView, self).get_context_data(**kwargs)
        context['type_choices'] = Target.TARGET_TYPES
        return context

    def post(self, request):
        super(CustomTargetCreateView, self).post(request)
        return redirect(self.get_success_url())
    
    def form_valid(self, form):
        # First, create the targets in both dbs and nothing else
        with transaction.atomic():
            if form.is_valid():
                groups = [g.name for g in form.cleaned_data['groups']]
                self.object = form.save(form)

                # Sync with SNEx1
                db_session = _return_session()
                run_hook('target_post_save', target=self.object, created=True, group_names=groups, wrapped_session=db_session)
                db_session.commit()
            else:
                logger.info('Submitting target failed with errors {}'.format(form.errors))
                return super().form_invalid(form)

        # If that works, ingest extra stuff for SNEx2 target only
        # Run in separate atomic transaction block to avoid rolling back
        # target creation if extra data ingestion goes wrong
        with transaction.atomic():
            run_hook('target_post_save', target=self.object, created=False)

        return redirect(self.get_success_url())


class CustomDataProductUploadView(DataProductUploadView):

    form_class = CustomDataProductUploadForm

    def form_valid(self, form):

        target = form.cleaned_data['target']
        if not target:
            observation_record = form.cleaned_data['observation_record']
            target = observation_record.target
        else:
            observation_record = None
        dp_type = form.cleaned_data['data_product_type']
        data_product_files = self.request.FILES.getlist('files')
        successful_uploads = []
        for f in data_product_files:
            dp = DataProduct(
                target=target,
                observation_record=observation_record,
                data=f,
                product_id=None,
                data_product_type=dp_type
            )
            dp.save()
            try:
                #run_hook('data_product_post_upload', dp)

                ### ------------------------------------------------------------------
                ### Create row in ReducedDatumExtras with the extra info
                rdextra_value = {'data_product_id': int(dp.id)}
                if dp_type == 'photometry':
                    extras = {'reduction_type': 'manual'}
                    rdextra_value['photometry_type'] = form.cleaned_data['photometry_type']
                    background_subtracted = form.cleaned_data['background_subtracted']
                    if background_subtracted:
                        extras['background_subtracted'] = True
                        extras['subtraction_algorithm'] = form.cleaned_data['subtraction_algorithm']
                        extras['template_source'] = form.cleaned_data['template_source']

                else: #Don't need to append anything to reduceddatum value if not photometry
                    extras = {}
                rdextra_value['instrument'] = form.cleaned_data['instrument']
                reducer_group = form.cleaned_data['reducer_group']
                if reducer_group != 'LCO':
                    rdextra_value['reducer_group'] = reducer_group

                used_in = form.cleaned_data['used_in']
                if used_in:
                    rdextra_value['used_in'] = int(used_in.id)
                rdextra_value['final_reduction'] = form.cleaned_data['final_reduction']
                reduced_data = run_custom_data_processor(dp, extras)
                reduced_datum_extra = ReducedDatumExtra(
                    target = target,
                    data_type = dp_type,
                    key = 'upload_extras',
                    value = json.dumps(rdextra_value)
                )
                reduced_datum_extra.save()

                ### -------------------------------------------------------------------
                
                if not settings.TARGET_PERMISSIONS_ONLY:
                    for group in form.cleaned_data['groups']:
                        assign_perm('tom_dataproducts.view_dataproduct', group, dp)
                        assign_perm('tom_dataproducts.delete_dataproduct', group, dp)
                        assign_perm('tom_dataproducts.view_reduceddatum', group, reduced_data)
                successful_uploads.append(str(dp))
            except InvalidFileFormatException as iffe:
                ReducedDatum.objects.filter(data_product=dp).delete()
                dp.delete()
                ReducedDatumExtra.objects.filter(target=target, value=json.dumps(rdextra_value)).delete()
                messages.error(
                    self.request,
                    'File format invalid for file {0} -- error was {1}'.format(str(dp), iffe)
                )
            except Exception as e:
                ReducedDatum.objects.filter(data_product=dp).delete()
                dp.delete()
                ReducedDatumExtra.objects.filter(target=target, value=json.dumps(rdextra_value)).delete()
                messages.error(self.request, 'There was a problem processing your file: {0}'.format(str(dp)))
                print(e)
        if successful_uploads:
            messages.success(
                self.request,
                'Successfully uploaded: {0}'.format('\n'.join([p for p in successful_uploads]))
            )

        return redirect(form.cleaned_data.get('referrer', '/'))


class CustomDataProductDeleteView(DataProductDeleteView):

    def delete(self, request, *args, **kwargs):
        rd = ReducedDatum.objects.filter(data_product=self.get_object())
        for r in rd:
            data_type = r.data_type
            r.delete()
        # Delete the ReducedDatumExtra row
        reduced_datum_query = ReducedDatumExtra.objects.filter(data_type=data_type, key='upload_extras')
        for row in reduced_datum_query:
            value = json.loads(row.value) 
            if value.get('data_product_id', '') == int(self.get_object().id):
                row.delete()
                break
        self.get_object().data.delete()
        return super().delete(request, *args, **kwargs)


def save_dataproduct_groups_view(request):
    group_names = json.loads(request.GET.get('groups', None))
    dataproduct_id = request.GET.get('dataproductid', None)
    dp = DataProduct.objects.get(id=dataproduct_id)
    data = ReducedDatum.objects.filter(data_product=dp)
    successful_groups = ''
    for i in group_names:
        group = Group.objects.get(name=i)
        assign_perm('tom_dataproducts.view_dataproduct', group, dp)
        for datum in data:
            assign_perm('tom_dataproducts.view_reduceddatum', group, datum)
        successful_groups += i
    response_data = {'success': successful_groups}
    return HttpResponse(json.dumps(response_data), content_type='application/json')


class Snex1ConnectionError(Exception):
    def __init__(self, message="Error syncing with the SNEx1 database"):
        self.message = message
        super().__init__(self.message)


class PaperCreateView(FormView):
    
    form_class = PapersForm
    template_name = 'custom_code/papers_list.html'

    def form_valid(self, form):
        target = form.cleaned_data['target']
        first_name = form.cleaned_data['author_first_name']
        last_name = form.cleaned_data['author_last_name']
        status = form.cleaned_data['status']
        description = form.cleaned_data['description']
        paper = Papers(
                target=target,
                author_first_name=first_name,
                author_last_name=last_name,
                status=status,
                description=description
            )
        paper.save()
        run_hook('sync_paper_with_snex1', paper)
        
        return HttpResponseRedirect('/targets/{}/'.format(target.id))


def save_comments(comment, object_id, user, tablename='observationgroup'):

    try:
        if tablename == 'observationgroup':
            content_type_id = ContentType.objects.get(model='observationgroup').id
        else:
            tablename_dict = {'spec': 'reduceddatum',
                              'target': 'targets'}
            snex2_model = tablename_dict[tablename]
            content_type_id = ContentType.objects.get(model=snex2_model).id

        newcomment = Comment(
            object_pk=object_id,
            user_name=user.username,
            user_email=user.email,
            comment=comment,
            submit_date=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'),
            is_public=True,
            is_removed=False,
            content_type_id=content_type_id,
            site_id=2,
            user_id=user.id
        )
        newcomment.save()
        return True
    except:
        return False


def save_comments_view(request):
    comment = request.GET['comment']
    object_id = int(request.GET['object_id'])
    user_id = int(request.GET['user_id'])
    tablename = request.GET['tablename']

    user = User.objects.get(id=user_id)

    saved = save_comments(comment, object_id, user, tablename=tablename)

    if saved:
        if tablename == 'spec':
            ### Save comment in SNEx1 as well
            spec = ReducedDatum.objects.get(id=object_id)
            target_id = int(spec.target_id)
            snex_id_row = ReducedDatumExtra.objects.filter(data_type='spectroscopy', key='snex_id', target_id=target_id, value__icontains='"snex2_id": {}'.format(object_id)).first()
            if snex_id_row:
                snex1_id = json.loads(snex_id_row.value)['snex_id']
                run_hook('sync_comment_with_snex1', comment, 'spec', user_id, target_id, snex1_id)
        
        return HttpResponse(json.dumps({'success': 'Saved'}))
    
    else:
        return HttpResponse(json.dumps({'failure': 'Failed to save'}))


def cancel_observation(obs):
    
    facility = get_service_class(obs.facility)()
    
    if obs.status not in TERMINAL_OBSERVING_STATES:
        success = facility.cancel_observation(obs.observation_id)
        if not success:
            return False

        obs.status = 'CANCELED'
        obs.save()
    
    ## Change status of DynamicCadence
    obs_group = obs.observationgroup_set.first()
    dynamic_cadence = DynamicCadence.objects.get(observation_group=obs_group)
    dynamic_cadence.active = False
    dynamic_cadence.save()

    ## Update sequence end time in template record
    template = obs_group.observation_records.filter(observation_id='template').first()
    if template:
        template.parameters['sequence_end'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        template.save()
    
    return True


def observation_sequence_cancel_view(request):
    
    obsr_id = int(float(request.GET['pk']))
    obsr = ObservationRecord.objects.get(id=obsr_id)
    # obsr is the template observation record, so need to get the most recent one from this sequence to cancel
    last_obs = obsr.observationgroup_set.first().observation_records.all().exclude(observation_id__contains='template').order_by('-id').first()

    if last_obs:
        canceled = cancel_observation(last_obs)
        
        if not canceled:
            response_data = {'failure': 'Error'}
            return HttpResponse(json.dumps(response_data), content_type='application/json')
    
    ## Run hook to cancel old sequence in SNEx1
    try:
        obs_group = obsr.observationgroup_set.first()
        snex_id = int(obs_group.name)
        # Get comments, if any
        comments = json.loads(request.GET['comment'])
        if comments.get('cancel', ''):
            save_comments(comments['cancel'], obs_group.id, request.user)
            run_hook('cancel_sequence_in_snex1', 
                     snex_id, 
                     comment=comments['cancel'],
                     tableid=snex_id,
                     userid=request.user.id,
                     targetid=obsr.target_id)
        else:
            run_hook('cancel_sequence_in_snex1', snex_id, userid=request.user.id)
    except:
        logger.error('This sequence was not in SNEx1 or was not canceled')
    
    response_data = {'success': 'Modified'}
    return HttpResponse(json.dumps(response_data), content_type='application/json')


def approve_or_reject_observation_view(request):
    
    obsr_id = int(float(request.GET['pk']))
    status = request.GET['status']
    obsr = ObservationRecord.objects.get(id=obsr_id)
    obsr.observation_id = 'template'
    obsr.save()

    obs_group = obsr.observationgroup_set.first()

    if status == 'approved':
        ## Set the cadence to active in SNEx2 and approve it in SNEx1
        cadence = DynamicCadence.objects.get(observation_group_id=obs_group.id)
        cadence.active = True
        cadence.save()
        
        try:
            snex_id = int(obs_group.name)
            run_hook('approve_sequence_in_snex1', snex_id)
        except:
            response_data = {'failure': 'Error'}
            logger.error('This sequence was not in SNEx1 or was not canceled')
            return HttpResponse(json.dumps(response_data), content_type='application/json')
    
    elif status == 'rejected':
        ## Set the end time for the template in SNEx2, and cancel it in SNEx1
        obsr.parameters['sequence_end'] = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S')
        obsr.save()
        
        comments = json.loads(request.GET['comment'])
        try:
            snex_id = int(obs_group.name)
            if comments.get('cancel', ''):
                save_comments(comments['cancel'], obs_group.id, request.user)
                run_hook('cancel_sequence_in_snex1', 
                         snex_id, 
                         comment=comments['cancel'],
                         tableid=snex_id,
                         userid=request.user.id,
                         targetid=obsr.target_id)
            else:
                run_hook('cancel_sequence_in_snex1', snex_id, userid=request.user.id)
        except:
            response_data = {'failure': 'Error'}
            logger.error('This sequence was not in SNEx1 or was not canceled')
            return HttpResponse(json.dumps(response_data), content_type='application/json')
     
    response_data = {'success': 'Modified'}
    return HttpResponse(json.dumps(response_data), content_type='application/json')


def scheduling_view(request):

    if 'modify' in request.GET['button']:
        obs_id = int(float(request.GET['observation_id']))
        obs = ObservationRecord.objects.get(id=obs_id)

        ## Get the new observation parameters
        form_data = {'name': request.GET['name'],
                     'target_id': int(float(request.GET['target_id'])),
                     'facility': request.GET['facility'],
                     'observation_type': request.GET['observation_type']
            }

        observing_parameters = json.loads(request.GET['observing_parameters'])
        # Append the additional info that users can change to parameters
        observing_parameters['ipp_value'] = float(request.GET['ipp_value'])
        observing_parameters['max_airmass'] = float(request.GET['max_airmass'])
        observing_parameters['cadence_strategy'] = request.GET.get('cadence_strategy', '')
        observing_parameters['cadence_frequency'] = float(request.GET['cadence_frequency'])
        observing_parameters['reminder'] = float(request.GET['reminder']) #Observing form turns this into timestamp
        observing_parameters['facility'] = obs.facility
        observing_parameters['name'] = form_data['name']
        observing_parameters['target_id'] = form_data['target_id']
        observing_parameters['delay_start'] = True
        observing_parameters['delay_amount'] = float(request.GET['delay_start'])
        
        now = datetime.utcnow()
        observing_parameters['start'] = datetime.strftime(now + timedelta(days=float(request.GET['delay_start'])), '%Y-%m-%dT%H:%M:%S')
        observing_parameters['end'] = datetime.strftime(now + timedelta(hours=float(request.GET['cadence_frequency'])*24+float(request.GET['delay_start'])*24), '%Y-%m-%dT%H:%M:%S')

        if request.GET['observation_type'] == 'IMAGING':
            filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
            for f in filters:
                if f+'_0' in request.GET.keys() and float(request.GET[f+'_0'][0]) > 0.0:
                    observing_parameters[f] = [float(request.GET[f+'_0']), int(float(request.GET[f+'_1'])), int(float(request.GET[f+'_2']))]

        elif request.GET['observation_type'] == 'SPECTRA':
            observing_parameters['exposure_time'] = int(float(request.GET['exposure_time']))

        if request.GET['cadence_strategy']: 
            cadence = {'cadence_strategy': request.GET['cadence_strategy'],
                       'cadence_frequency': float(request.GET['cadence_frequency'])
                }
            form_data['cadence'] = cadence 
        form_data['observing_parameters'] = observing_parameters

        # Make sure at least one of the observing parameters changed
        dict_keys = ['ipp_value', 'max_airmass', 'cadence_frequency', 'U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w', 'exposure_time']
        modified = False
        for key in dict_keys:
            if key in observing_parameters.keys() and key in obs.parameters.keys():
                if observing_parameters[key] != obs.parameters[key]:
                    modified = True
                    break
        if not modified:
            response_data = {'failure': 'Sequence parameters were not modified, please modify one and try again'}
            return HttpResponse(json.dumps(response_data), content_type='application/json')

        ### Begin atomic transaction here
        try:
            db_session = _return_session()
            with transaction.atomic():
                
                ### Get SNEx1 db session
                
                # Cancel the old observation
                canceled = cancel_observation(obs)
                if not canceled:
                    response_data = {'failure': 'Canceling the previous sequence failed, please try again'}
                    raise Snex1ConnectionError(message='Could not cancel previous sequence')
                    #return HttpResponse(json.dumps(response_data), content_type='application/json')
        
                # Submission follows how observation requests are submitted in TOM view
                facility = get_service_class(obs.facility)()
                form = facility.get_form(form_data['observation_type'])(observing_parameters)
                if form.is_valid():
                    observation_ids = facility.submit_observation(form.observation_payload())
                else:
                    logger.error(msg=f'Unable to submit next cadenced observation: {form.errors}')
                    response_data = {'failure': 'Unable to submit next cadenced observation'}
                    raise Snex1ConnectionError(message='Observation portal returned errors {}'.format(form.errors))
                    #return HttpResponse(json.dumps(response_data), content_type='application/json')

                # Creation of corresponding ObservationRecord objects for the observations
                new_observations = []
                for observation_id in observation_ids:
                    # Create Observation record
                    record = ObservationRecord.objects.create(
                        target=Target.objects.get(id=form_data['target_id']),
                        facility=facility.name,
                        parameters=form.serialize_parameters(),#observing_parameters,
                        observation_id=observation_id
                    )
                    new_observations.append(record)
        
                if len(new_observations) > 1 or form_data.get('cadence'):
                    observation_group = ObservationGroup.objects.create(name=form_data['name'])
                    observation_group.observation_records.add(*new_observations)
                    assign_perm('tom_observations.view_observationgroup', request.user, observation_group)
                    assign_perm('tom_observations.change_observationgroup', request.user, observation_group)
                    assign_perm('tom_observations.delete_observationgroup', request.user, observation_group)

                    if form_data.get('cadence'):
                        DynamicCadence.objects.create(
                            observation_group=observation_group,
                            cadence_strategy=cadence.get('cadence_strategy'),
                            cadence_parameters={'cadence_frequency': float(request.GET['cadence_frequency'])},
                            active=True
                        )

                if not settings.TARGET_PERMISSIONS_ONLY:
                    group_id_list = list(GroupObjectPermission.objects.filter(object_pk=obs_id).values_list('group_id', flat=True).distinct())
                    groups = Group.objects.filter(id__in=group_id_list)
                    for record in new_observations:
                        assign_perm('tom_observations.view_observationrecord', groups, record)
                        assign_perm('tom_observations.change_observationrecord', groups, record)
                        assign_perm('tom_observations.delete_observationrecord', groups, record)
        
                ### Sync with SNEx1
                ## Run hook to cancel old sequence in SNEx1
                obs_group = obs.observationgroup_set.first()
                snex_id = int(obs_group.name)
            
                # Get comments, if any
                comments = json.loads(request.GET['comment'])
                if comments.get('cancel', ''):
                    save_comments(comments['cancel'], obs_group.id, request.user)
                    run_hook('cancel_sequence_in_snex1',
                             snex_id,
                             comment=comments['cancel'],
                             tableid=snex_id,
                             userid=request.user.id,
                             targetid=obs.target_id,
                             wrapped_session=db_session)
                else:
                    run_hook('cancel_sequence_in_snex1', 
                             snex_id, 
                             userid=request.user.id, 
                             wrapped_session=db_session)
        
                # Get the group ids to pass to SNEx1
                group_names = []
                if not settings.TARGET_PERMISSIONS_ONLY:
                    for group in groups:
                        group_names.append(group.name)
        
                # Run the hook to add the sequence to SNEx1
                # Get comments, if any
                snex_id = run_hook(
                        'sync_sequence_with_snex1', 
                        form.serialize_parameters(), 
                        group_names, 
                        userid=request.user.id,
                        wrapped_session=db_session)
        
                # Change the name of the observation group, if one was created
                if len(new_observations) > 1 or form_data.get('cadence'):
                    observation_group.name = str(snex_id)
                    observation_group.save()

                    for record in new_observations:
                        record.parameters['name'] = snex_id
                        record.save()
            
                # Now run the hook to add each observation record to SNEx1
                for record in new_observations:
                    # Get the requestsgroup ID from the LCO API using the observation ID
                    obs_id = int(record.observation_id)
                    LCO_SETTINGS = settings.FACILITIES['LCO']
                    PORTAL_URL = LCO_SETTINGS['portal_url']
                    portal_headers = {'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}

                    query_params = urlencode({'request_id': obs_id})

                    r = requests.get('{}/api/requestgroups?{}'.format(PORTAL_URL, query_params), headers=portal_headers)
                    requestgroups = r.json()
                    if requestgroups['count'] == 1:
                        requestgroup_id = int(requestgroups['results'][0]['id'])

                    run_hook('sync_observation_with_snex1', snex_id, record.parameters, requestgroup_id, wrapped_session=db_session)
                
                response_data = {'success': 'Modified'}
                db_session.commit()

        except Exception as e: 
            logger.error('Syncing with the SNEx1 database failed for target {} with error {}'.format(obs.target_id, e))
            db_session.rollback()
        
        finally:
            db_session.close()
        
        ### End of the atomic transaction
        return HttpResponse(json.dumps(response_data), content_type='application/json')

    elif 'continue' in request.GET['button']:
        logger.info('Continuing Sequence as-is')
        observation_id = int(float(request.GET['observation_id']))
        obs = ObservationRecord.objects.get(id=observation_id)
        
        ## Check to make sure no parameters were updated
        observing_parameters = {}
        observing_parameters['ipp_value'] = float(request.GET['ipp_value'])
        observing_parameters['max_airmass'] = float(request.GET['max_airmass'])
        observing_parameters['cadence_frequency'] = float(request.GET['cadence_frequency'])
        
        if request.GET['observation_type'] == 'IMAGING':
            filters = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
            for f in filters:
                if f+'_0' in request.GET.keys() and float(request.GET[f+'_0'][0]) > 0.0:
                    observing_parameters[f] = [float(request.GET[f+'_0']), int(float(request.GET[f+'_1'])), int(float(request.GET[f+'_2']))]

        elif request.GET['observation_type'] == 'SPECTRA':
            observing_parameters['exposure_time'] = int(float(request.GET['exposure_time']))
        
        dict_keys = ['ipp_value', 'max_airmass', 'cadence_frequency', 'U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w', 'exposure_time']
        modified = False
        for key in dict_keys:
            if key in observing_parameters.keys() and key in obs.parameters.keys():
                if observing_parameters[key] != obs.parameters[key]:
                    modified = True
                    break
        if modified:
            response_data = {'failure': 'Sequence parameters were modified. If this was intentional, please press the "Modify Sequence" button instead.'}
            return HttpResponse(json.dumps(response_data), content_type='application/json')

        ## Only update the reminder parameter in ObservationRecord
        try:
            db_session = _return_session()
            with transaction.atomic():
                next_reminder = float(request.GET['reminder'])
                obs_parameters = obs.parameters
                now = datetime.now()
                obs_parameters['reminder'] = datetime.strftime(now + timedelta(days=next_reminder), '%Y-%m-%dT%H:%M:%S')
                obs.parameters = obs_parameters
                obs.save()
                
                ## Run hook to update the reminder in SNEx1
                obsgroup = obs.observationgroup_set.first()
                snex_id = int(obsgroup.name)
                run_hook('update_reminder_in_snex1', snex_id, next_reminder, wrapped_session=db_session)
                response_data = {'success': 'Continued'}
                db_session.commit()

        except:
            message = 'This sequence was not in SNEx1 or the reminder was not updated'
            logger.error(message)
            response_data = {'failure': message}
            db_session.rollback()

        finally:
            db_session.close()
                
        return HttpResponse(json.dumps(response_data), content_type='application/json')
    
    elif 'stop' in request.GET['button']:
        logger.info('Stopping Sequence')
        ## Cancel observation request in LCO portal
        try:
            db_session = _return_session()
            with transaction.atomic():
                obs_id = int(float(request.GET['observation_id']))
                obs = ObservationRecord.objects.get(id=obs_id)
                canceled = cancel_observation(obs)
                if not canceled:
                    response_data = {'failure': 'This sequence could not be canceled in SNEx1'} 
                    raise Snex1ConnectionError(message='This sequence could not be canceled in SNEx1')
                ## Run hook to cancel this sequence in SNEx1
                obs_group = obs.observationgroup_set.first()
                snex_id = int(obs_group.name)

                # Get comments, if any
                comments = json.loads(request.GET['comment'])
                if comments.get('cancel', ''):
                    save_comments(comments['cancel'], obs_group.id, request.user)
                    run_hook('cancel_sequence_in_snex1', 
                             snex_id, 
                             comment=comments['cancel'],
                             tableid=snex_id,
                             userid=request.user.id,
                             targetid=obs.target_id,
                             wrapped_session=db_session)
                else:
                    run_hook('cancel_sequence_in_snex1', snex_id, userid=request.user.id, wrapped_session=db_session)
        
                response_data = {'success': 'Stopped'}
                db_session.commit()
        
        except:
            message = 'This sequence was not in SNEx1 or was not canceled'
            logger.error(message)
            response_data = {'failure': message}
            db_session.rollback()

        finally:
            db_session.close()

        return HttpResponse(json.dumps(response_data), content_type='application/json')


def change_target_known_to_view(request):
    action = request.GET.get('action')
    group_name = request.GET.get('group')
    group = Group.objects.get(name=group_name)
    target_name = request.GET.get('target')
    target = Target.objects.get(name=target_name)
    
    if target not in get_objects_for_user(request.user, 'tom_targets.change_target'):
        response_data = {'failure': 'Error'}
        return HttpResponse(json.dumps(response_data), content_type='application/json')

    if action == 'add':
        # Add permissions for this group
        assign_perm('tom_targets.view_target', group, target)
        assign_perm('tom_targets.change_target', group, target)
        assign_perm('tom_targets.delete_target', group, target)
        response_data = {'success': 'Added'}
        return HttpResponse(json.dumps(response_data), content_type='application/json')

    elif action == 'remove':
        # Remove permissions for this group
        remove_perm('tom_targets.view_target', group, target)
        remove_perm('tom_targets.change_target', group, target)
        remove_perm('tom_targets.delete_target', group, target)
        response_data = {'success': 'Removed'}
        return HttpResponse(json.dumps(response_data), content_type='application/json')
        

class ReferenceStatusUpdateView(FormView):

    form_class = ReferenceStatusForm
    template_name = 'custom_code/reference_status.html'

    def form_valid(self, form):
        target_id = form.cleaned_data['target']
        target = Target.objects.get(id=target_id)
        status = form.cleaned_data['status']
        old_status_query = TargetExtra.objects.filter(target=target, key='reference')
        if not old_status_query:
            reference = TargetExtra(
                    target=target,
                    key='reference',
                    value=status
                )
            reference.save()

        else:
            old_status = old_status_query.first()
            old_status.value = status
            old_status.save()
            
        return HttpResponseRedirect('/targets/{}/'.format(target.id))


def change_interest_view(request):
    target_name = request.GET.get('target')
    target = Target.objects.get(name=target_name)
    user = request.user

    interested_persons = [p.user for p in InterestedPersons.objects.filter(target=target)]
    if user in interested_persons:
        user_interest_row = InterestedPersons.objects.get(target=target, user=user)
        user_interest_row.delete()

        run_hook('change_interest_in_snex1', target.id, user.username, 'uninterested')

        response_data = {'success': 'Uninterested'}
        return HttpResponse(json.dumps(response_data), content_type='application/json')

    else:
        user_interest_row = InterestedPersons(target=target, user=user)
        user_interest_row.save()

        run_hook('change_interest_in_snex1', target.id, user.username, 'interested')
        
        response_data = {'success': 'Interested',
                         'name': user.get_full_name()
                    }
        return HttpResponse(json.dumps(response_data), content_type='application/json')


def search_name_view(request):

    search_entry = request.GET.get('name')
    logger.info("searching for {}".format(search_entry))
    context = {}
    if search_entry:
        target_match_list = Target.objects.filter(Q(name__icontains=search_entry) | Q(aliases__name__icontains=search_entry)).distinct()

    else:
        target_match_list = Target.objects.none()

    context['targets'] = target_match_list

    if request.is_ajax():
        html = render_to_string(
            template_name='custom_code/partials/name-search-results.html',
            context={'targets': target_match_list}
        )

        data_dict = {"html_from_view": html}

        return JsonResponse(data=data_dict, safe=False)
    return render(request, 'tom_targets/target_grouping.html', context=context)


def async_spectra_page_view(request):
    target_id = request.GET.get('target_id')
    if target_id:
        target = Target.objects.get(id=target_id)
        response = dash_spectra_page({'request': request}, target)
        if 'dash_context' in response.keys():
            context = {'plot_list': [],
                       'request': request
            }
        else:
            context = {'plot_list': response['plot_list'],
                       'request': request
            }

        html = render_to_string(
            template_name='custom_code/dash_spectra_page.html',
            context=context
        )
        data_dict = {'html_from_view': html}

        return JsonResponse(data=data_dict, safe=False)
    return ''


def async_scheduling_page_view(request):
    obs_ids = json.loads(request.GET['obs_ids'])
    all_html = ''
    for obs_id in obs_ids:
        obs = ObservationRecord.objects.get(id=obs_id)
        response = scheduling_list_with_form({'request': request}, obs, case='nonpending')

        html = render_to_string(
            template_name='custom_code/scheduling_list_with_form.html',
            context=response,
            request=request
        )

        all_html += html

    data_dict = {'html_from_view': all_html}
    
    return JsonResponse(data=data_dict, safe=False)


def add_target_to_group_view(request):
    target_name = request.GET.get('target_name')
    target = Target.objects.get(name=target_name)
    
    targetlist_id = request.GET.get('group_id')
    targetlist = TargetList.objects.get(id=targetlist_id)

    list_type = request.GET.get('list')

    if request.user.has_perm('tom_targets.view_target', target) and target not in targetlist.targets.all():

        if list_type == 'observing_run':
            if len(targetlist.targets.all()) == 0:
                target_priority = 1
            else:
                target_priority = max([t.extra_fields['observing_run_priority'] for t in targetlist.targets.all()]) + 1

            new_target_priority = TargetExtra(target=target, key='observing_run_priority', value=target_priority)
            new_target_priority.save()
        
        targetlist.targets.add(target)
    
    response_data = {'success': 'Added'}
    return HttpResponse(json.dumps(response_data), content_type='application/json') 


def remove_target_from_group_view(request):
    target_id = request.GET.get('target_id')
    target = Target.objects.get(id=target_id)
    
    targetlist_id = request.GET.get('group_id')
    targetlist = TargetList.objects.get(id=targetlist_id)
    
    list_type = request.GET.get('list')

    if request.user.has_perm('tom_targets.view_target', target) and target in targetlist.targets.all():
        targetlist.targets.remove(target)

        if list_type == 'observing_run': 
            old_priority = TargetExtra.objects.get(target=target, key='observing_run_priority')
            try:
                old_priority_value = int(old_priority.value)
            except:
                old_priority_value = int(float(old_priority.value))
 
            if len(targetlist.targets.all()) > 0:
                for t in targetlist.targets.all():
                    this_target_priority_value = t.extra_fields['observing_run_priority']
                    if this_target_priority_value > old_priority_value:
                        this_target_new_priority = this_target_priority_value - 1
                        this_target_priority = TargetExtra.objects.get(target=t, key='observing_run_priority')
                        this_target_priority.value = this_target_new_priority
                        this_target_priority.save()
            
            old_priority.delete()
        
    response_data = {'success': 'Removed'}
    return HttpResponse(json.dumps(response_data), content_type='application/json') 


def change_observing_priority_view(request):
    target_id = request.GET.get('target_id')
    target = Target.objects.get(id=target_id)

    targetlist_id = request.GET.get('group_id')
    targetlist = TargetList.objects.get(id=targetlist_id)

    try:
        new_priority = int(request.GET.get('priority'))
    except:
        new_priority = int(float(request.GET.get('priority')))

    target_priority = TargetExtra.objects.get(target=target, key='observing_run_priority')
    target_priority.value = new_priority
    target_priority.save()

    for t in targetlist.targets.all():
        if t == target:
            continue
        t_priority = TargetExtra.objects.get(target=t, key='observing_run_priority')
        try:
            this_obj_priority = int(t_priority.value)
        except:
            this_obj_priority = int(float(t_priority.value))
        if this_obj_priority >= new_priority:
            t_priority.value = this_obj_priority + 1
            t_priority.save()
    return HttpResponseRedirect('/targets/targetgrouping/')


class CustomObservationListView(ObservationListView):

    def get_queryset(self, *args, **kwargs):
        """
        Gets the most recent ObservationRecord objects associated with active
        DynamicCadences that the user has permission to view
        """
        try:
            obsrecordlist = [c.observation_group.observation_records.order_by('-created').first() for c in DynamicCadence.objects.filter(active=True)]
        except Exception as e:
            logger.info(e)
            obsrecordlist = []
        obsrecordlist_ids = [o.id for o in obsrecordlist if o is not None and self.request.user in get_users_with_perms(o)]
        return ObservationRecord.objects.filter(id__in=obsrecordlist_ids)


class ObservationListExtrasView(ListView):
    """
    View that displays all active sequences by either IPP or urgency
    """
    template_name = 'custom_code/observation_list_extras.html'
    paginate_by = 10
    model = ObservationRecord
    strict = False
    context_object_name = 'observation_list'

    def get_queryset(self, *args, **kwargs):
        """
        Get all active cadences and order their observation records in order of IPP or urgency
        """
        val = self.kwargs['key']
        
        if val == 'ipp':
            try:
                obsrecordlist = [c.observation_group.observation_records.order_by('-created').first() for c in DynamicCadence.objects.filter(active=True)]
            except Exception as e:
                logger.info(e)
                obsrecordlist = []
            obsrecordlist_ids = [o.id for o in obsrecordlist if o is not None and self.request.user in get_users_with_perms(o)]
            obsrecords = ObservationRecord.objects.filter(id__in=obsrecordlist_ids)
            obsrecords = obsrecords.annotate(ipp=KeyTextTransform('ipp_value', 'parameters'))
            return obsrecords.order_by('-ipp')
        
        elif val == 'urgency':
            try:
                obsrecordlist = [c.observation_group.observation_records.filter(status='COMPLETED').order_by('-created').first() for c in DynamicCadence.objects.filter(active=True)]
            except Exception as e:
                logger.info(e)
                obsrecordlist = []
            obsrecordlist_ids = [o.id for o in obsrecordlist if o is not None and self.request.user in get_users_with_perms(o)]
            obsrecords = ObservationRecord.objects.filter(id__in=obsrecordlist_ids)
            now = datetime.utcnow()
            recent_obs = obsrecords.annotate(days_since=now-Cast(KeyTextTransform('start', 'parameters'), DateTimeField()))
            recent_obs = recent_obs.annotate(cadence=KeyTextTransform('cadence_frequency', 'parameters'))
            recent_obs = recent_obs.filter(cadence__gt=0.0)
            recent_obs = recent_obs.annotate(urgency=ExpressionWrapper(F('days_since')/(Cast(KeyTextTransform('cadence_frequency', 'parameters'), FloatField())), DateTimeField()))
            return recent_obs.order_by('-urgency')

    
    def get_context_data(self, *args, **kwargs):
        
        context = super().get_context_data(*args, **kwargs)
        context['value'] = self.kwargs['key'].upper()
        return context


class CustomObservationCreateView(ObservationCreateView):

    def get_form(self):
        """
        Gets an instance of the form appropriate for the request.
        :returns: observation form
        :rtype: subclass of GenericObservationForm
        """
        form = super().get_form()
        if not settings.TARGET_PERMISSIONS_ONLY:
            form.fields['groups'].queryset = Group.objects.all()
        form.helper.form_action = reverse(
            'submit-lco-obs', kwargs={'facility': 'LCO'}
        )
        return form
    
    
    def form_valid(self, form):
        """
        Runs after form validation. Submits the observation to the desired facility and creates an associated
        ``ObservationRecord``, then writes this sequence and record to the SNEx1 database,
        and finally redirects to the detail page of the target to be observed.
        If the facility returns more than one record, a group is created and all observation
        records from the request are added to it.
        :param form: form containing observating request parameters
        :type form: subclass of GenericObservationForm
        """
        # Submit the observation
        facility = self.get_facility_class()
        target = self.get_target()
        observation_ids = facility().submit_observation(form.observation_payload())
        records = []

        for observation_id in observation_ids:
            # Create Observation record
            record = ObservationRecord.objects.create(
                target=target,
                user=self.request.user,
                facility=facility.name,
                parameters=form.serialize_parameters(),
                observation_id=observation_id
            )
            records.append(record)

        if len(records) > 1 or form.cleaned_data.get('cadence_strategy'):
            observation_group = ObservationGroup.objects.create(name=form.cleaned_data['name'])
            observation_group.observation_records.add(*records)
            assign_perm('tom_observations.view_observationgroup', self.request.user, observation_group)
            assign_perm('tom_observations.change_observationgroup', self.request.user, observation_group)
            assign_perm('tom_observations.delete_observationgroup', self.request.user, observation_group)

            if form.cleaned_data.get('cadence_strategy'):
                cadence_parameters = {}
                cadence_form = get_cadence_strategy(form.cleaned_data.get('cadence_strategy')).form
                for field in cadence_form().cadence_fields:
                    cadence_parameters[field] = form.cleaned_data.get(field)
                DynamicCadence.objects.create(
                    observation_group=observation_group,
                    cadence_strategy=form.cleaned_data.get('cadence_strategy'),
                    cadence_parameters=cadence_parameters,
                    active=True
                )

        if not settings.TARGET_PERMISSIONS_ONLY:
            groups = form.cleaned_data['groups']
            for record in records:
                assign_perm('tom_observations.view_observationrecord', groups, record)
                assign_perm('tom_observations.change_observationrecord', groups, record)
                assign_perm('tom_observations.delete_observationrecord', groups, record)
        
        ### Sync with SNEx1
        
        # Get the group ids to pass to SNEx1
        group_names = []
        for group in form.cleaned_data['groups']:
           group_names.append(group.name)
        
        # Run the hook to add the sequence to SNEx1
        if form.cleaned_data.get('comment') and (len(records) > 1 or form.cleaned_data.get('cadence_strategy')):
            save_comments(form.cleaned_data['comment'], observation_group.id, self.request.user.id)
            snex_id = run_hook('sync_sequence_with_snex1', 
                               form.serialize_parameters(), 
                               group_names, 
                               userid=self.request.user.id, 
                               comment=form.cleaned_data['comment'], 
                               targetid=target.id)
            
        else:
            snex_id = run_hook('sync_sequence_with_snex1', form.serialize_parameters(), group_names, userid=self.request.user.id)
        
        # Change the name of the observation group, if one was created
        if len(records) > 1 or form.cleaned_data.get('cadence_strategy'):
            observation_group.name = str(snex_id)
            observation_group.save()

            for record in records:
                record.parameters['name'] = snex_id
                record.save()
            
        # Now run the hook to add each observation record to SNEx1
        for record in records:
            # Get the requestsgroup ID from the LCO API using the observation ID
            obs_id = int(record.observation_id)
            LCO_SETTINGS = settings.FACILITIES['LCO']
            PORTAL_URL = LCO_SETTINGS['portal_url']
            portal_headers = {'Authorization': 'Token {0}'.format(LCO_SETTINGS['api_key'])}

            query_params = urlencode({'request_id': obs_id})

            r = requests.get('{}/api/requestgroups?{}'.format(PORTAL_URL, query_params), headers=portal_headers)
            requestgroups = r.json()
            if requestgroups['count'] == 1:
                requestgroup_id = int(requestgroups['results'][0]['id'])

            run_hook('sync_observation_with_snex1', snex_id, record.parameters, requestgroup_id)

        return redirect(
            reverse('tom_targets:detail', kwargs={'pk': target.id})
        )


def make_tns_request_view(request):
    target_id = request.GET.get('target_id')
    target = Target.objects.get(id=target_id)

    tns_params = _get_tns_params(target)
    if tns_params.get('success', ''):
        return HttpResponse(json.dumps(tns_params), content_type='application/json')
    else:
        logger.info('TNS parameters not ingested for target {}'.format(target_id))
        response_data = {'failure': 'TNS parameters not ingested for this target'}
        return HttpResponse(json.dumps(response_data), content_type='application/json')


def load_lightcurve_view(request):
    target = Target.objects.get(id=request.GET.get('target_id'))
    user = User.objects.get(id=request.GET.get('user_id'))

    lightcurve = lightcurve_with_extras(target, user)['plot']
    context = {'success': 'success',
               'lightcurve_plot': lightcurve
    }
    return HttpResponse(json.dumps(context), content_type='application/json')


def fit_lightcurve_view(request):

    target_id = request.GET.get('target_id', None)
    target = Target.objects.get(id=target_id)
    user_id = request.GET.get('user_id', None)
    user = User.objects.get(id=user_id)
    filt = request.GET.get('filter', None)
    days = float(request.GET.get('days', 20))

    fit = lightcurve_fits(target, user, filt, days)
    lightcurve_plot = fit['plot']
    fitted_max = fit['max']
    max_mag = fit['mag']
    fitted_filt = fit['filt']
    
    if fitted_max:

        fitted_date = date.strftime(Time(fitted_max, scale='utc', format='jd').datetime, "%m/%d/%Y")

        context = {
            'success': 'success',
            'lightcurve_plot': lightcurve_plot,
            'fitted_max': '{} ({})'.format(fitted_date, fitted_max),
            'max_mag': max_mag,
            'max_filt': fitted_filt
        }

    else:
        context = {
            'success': 'failure',
            'lightcurve_plot': lightcurve_plot,
            'fitted_max': fitted_max,
            'max_mag': max_mag,
            'max_filt': fitted_filt
        }

    return HttpResponse(json.dumps(context), content_type='application/json')


def save_lightcurve_params_view(request):

    target_id = request.GET.get('target_id', None)
    target = Target.objects.get(id=target_id)
    key = request.GET.get('key', None)
    
    # Delete any previously saved parameters for this target and keyword
    old_params = TargetExtra.objects.filter(target=target, key=key)
    for old_param in old_params:
        old_param.delete()

    if key == 'target_description':
        value = request.GET.get('value', None)
        
    else:
        datestring = request.GET.get('date', None)
        date = datestring.split()[0]
        jd = datestring.split()[1].replace('(', '').replace(')', '')
 
        value = json.dumps({'date': date,
                 'jd': jd,
                 'mag': request.GET.get('mag', None),
                 'filt': request.GET.get('filt', None),
                 'source': request.GET.get('source', None)})

    te = TargetExtra(
         target=target,
         key=key,
         value=value
    )
    te.save()
    logger.info('Saved {} for target {}'.format(key, target_id))

    return HttpResponse(json.dumps({'success': 'Saved'}), content_type='application/json')


class ObservationGroupDetailView(DetailView):
    """
    View for displaying the details and records associated with
    an ObservationGroup object
    """
    model = ObservationGroup

    def get_queryset(self, *args, **kwargs):
        """
        Gets set of ObservationGroup objects associated with targets that
        the current user is authorized to view
        """
        #return get_objects_for_user(self.request.user, 'tom_observations.view_observationgroup')
        obsgroupids = get_objects_for_user(self.request.user, 'tom_observations.view_observationrecord').order_by('observationgroup').values_list('observationgroup', flat=True).distinct()

        return ObservationGroup.objects.filter(id__in=obsgroupids)

    def get_context_data(self, *args, **kwargs):
        """
        Adds items to context object for this view, including the associated
        observation records in ascending order of creation date
        """
        context = super().get_context_data(*args, **kwargs)
        obs_records = self.object.observation_records.all().order_by('created')
        parameters = []
        for obs in obs_records:
            p = {'start': obs.parameters['start'].replace('T', ' '),
                 'end': obs.parameters.get('end', ''),
                 'status': obs.status,
                 'obs_id': obs.observation_id,
                 'cadence': obs.parameters['cadence_frequency'],
                 'site': obs.parameters.get('site', ''),
                 'instrument': obs.parameters['instrument_type'],
                 'proposal': obs.parameters['proposal'],
                 'ipp': obs.parameters['ipp_value'],
                 'airmass': obs.parameters['max_airmass']
            }
            first_filt = []
            other_filts = []
            for f in ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']:
                if f in obs.parameters.keys() and not obs.parameters[f]:
                    continue
                elif f in obs.parameters.keys() and obs.parameters[f][0]:
                    current_filt = obs.parameters[f]
                    if not first_filt:
                        first_filt = {
                            'filt': f, 
                            'exptime': current_filt[0], 
                            'numexp': current_filt[1], 
                            'blocknum': current_filt[2]
                        }
                    else:
                        other_filts.append({
                            'filt': f, 
                            'exptime': current_filt[0], 
                            'numexp': current_filt[1], 
                            'blocknum': current_filt[2]
                        })

            p['first_filter'] = first_filt
            p['other_filters'] = other_filts
            parameters.append(p)

        context['parameters'] = parameters
        context['records'] = self.object.observation_records.all().order_by('created')
        return context


#class BrokerTargetView(FilterView):
# 
#    template_name = 'custom_code/broker_query_targets.html'
#    model = BrokerTarget
#    paginate_by = 10
#    context_object_name = 'brokertargets'
#    strict = False
#    filterset_class = BrokerTargetFilter
#
#    def get_context_data(self, **kwargs):
#        context = super().get_context_data(**kwargs)
#        #jd_now = Time(datetime.utcnow()).jd
#        #TNS_URL = "https://www.wis-tns.org/object/"
#        #for target in context['object_list']:
#        #    logger.info('Getting context data for TNS Target %s', target)
#        #    target.coords = make_coords(target.ra, target.dec)
#        #    target.mag_lnd = make_lnd(target.lnd_maglim,
#        #        target.lnd_filter, target.lnd_jd, jd_now)
#        #    target.mag_recent = make_magrecent(target.all_phot, jd_now)
#        #    target.link = TNS_URL + target.name
#        return context


def query_swift_observations_view(request):
   target_id = request.GET['target_id']
   t = Target.objects.get(id=target_id)
   ra, dec = t.ra, t.dec

   #from swifttools.swift_too import Swift_ObsQuery
   #username, shared_secret = os.environ['SWIFT_USERNAME'], os.environ['SWIFT_SECRET']
   #query = Swift_ObsQuery()
   #query.username = username
   #query.shared_secret = shared_secret
   #query.ra, query.dec = ra, dec
   #query.radius = 5 / 60 #5 arcmin

   #if query.submit():
   #    logger.info('Queried Swift for target {}'.format(target_id))
   #else:
   #    logger.info('Querying Swift failed with status {}'.format(query.status))
   #    content_response = {'success': 'Failed'}

   #if len(query):
   #    content_response = {'success': 'Yes'}
   #else:
   #    content_response = {'success': 'No'}

   ### NOT CURRENTLY FUNCTIONAL
   content_response = {'success': 'No'}

   return HttpResponse(json.dumps(content_response), content_type='application/json')


def make_thumbnail_view(request):

    filename_dict = json.loads(request.GET['filenamedict'])
    zoom = float(request.GET['zoom'])
    sigma = float(request.GET['sigma'])

    if filename_dict['psfx'] < 9999 and filename_dict['psfy'] < 9999:
        f = make_thumb(['data/fits/'+filename_dict['filepath']+filename_dict['filename']+'.fits'], grow=zoom, spansig=sigma, x=filename_dict['psfx'], y=filename_dict['psfy'], ticks=True)
    else:
        f = make_thumb(['data/fits/'+filename_dict['filepath']+filename_dict['filename']+'.fits'], grow=zoom, spansig=sigma, x=1024, y=1024, ticks=False)

    with open('data/thumbs/'+f[0], 'rb') as imagefile:
        b64_image = base64.b64encode(imagefile.read())
        thumb = b64_image.decode('utf-8')

    content_response = {'success': 'Yes',
                        'thumb': 'data:image/png;base64,{}'.format(thumb),
                        'telescope': filename_dict['tele'],
                        'instrument': filename_dict['filename'].split('-')[1][:2],
                        'filter': filename_dict['filter'],
                        'exptime': filename_dict['exptime']
                    }

    return HttpResponse(json.dumps(content_response), content_type='application/json')


class InterestingTargetsView(ListView):

    template_name = 'custom_code/interesting_targets.html'
    model = Target
    context_object_name = 'global_interesting_targets'

    def get_queryset(self):
        interesting_targets_list = TargetList.objects.filter(name='Interesting Targets').first()
        if interesting_targets_list:
            global_interesting_targets = interesting_targets_list.targets.all()
            logger.info('Got list of global interesting targets')
            return global_interesting_targets
        else:
            return []

    def get_context_data(self, **kwargs):
        context = super(InterestingTargetsView, self).get_context_data(**kwargs)
        active_cadences = DynamicCadence.objects.filter(active=True)
        active_target_ids = [c.observation_group.observation_records.first().target.id for c in active_cadences]
        for target in context['global_interesting_targets']:
            target.best_name = get_best_name(target)
            target.classification = target_extra_field(target, 'classification')
            target.redshift = target_extra_field(target, 'redshift')
            target.description = target_extra_field(target, 'target_description')
            target.science_tags = ', '.join([s.tag for s in ScienceTags.objects.filter(id__in=[t.tag_id for t in TargetTags.objects.filter(target_id=target.id)])])
            if target.id in active_target_ids:
                target.active_cadences = 'Yes'
            else:
                target.active_cadences = 'No'
        logger.info('Finished getting context data for global interesting targets')

        context['personal_interesting_targets'] = [q.target for q in InterestedPersons.objects.filter(user=self.request.user)] 
        for target in context['personal_interesting_targets']:
            target.best_name = get_best_name(target)
            target.classification = target_extra_field(target, 'classification')
            target.redshift = target_extra_field(target, 'redshift')
            target.description = target_extra_field(target, 'target_description')
            target.science_tags = ', '.join([s.tag for s in ScienceTags.objects.filter(id__in=[t.tag_id for t in TargetTags.objects.filter(target_id=target.id)])])
            if target.id in active_target_ids:
                target.active_cadences = 'Yes'
            else:
                target.active_cadences = 'No'
        logger.info('Finished getting context data for personal interesting targets')
        context['interesting_group_id'] = TargetList.objects.get(name='Interesting Targets').id
        return context


def sync_targetextra_view(request):
    newdata = json.loads(request.GET.get('newdata'))
    if newdata['key'] != 'name':
        if newdata.get('id'):
            te = TargetExtra.objects.get(id=newdata['id'])
            run_hook('targetextra_post_save', te, False)
        else:
            te = TargetExtra.objects.get(key=newdata['key'], target_id=newdata['targetid'])
            run_hook('targetextra_post_save', te, True)
    else:
        name = TargetName.objects.get(target_id=newdata['targetid'], name=newdata['value'])
        run_hook('targetname_post_save', name, True)
    return HttpResponse(json.dumps({'success': 'Synced'}), content_type='application/json')


@receiver(comment_was_posted)
def target_comment_receiver(sender, **kwargs):
    posted_comment = kwargs['comment']
    comment = posted_comment.comment
    content_type = ContentType.objects.get(id=posted_comment.content_type_id).model
    if content_type == 'target':
        tablename = 'targets'
        target_id = int(posted_comment.object_pk)
        user_id = int(posted_comment.user_id)
        if not settings.DEBUG:
            run_hook('sync_comment_with_snex1', comment, tablename, user_id, target_id, target_id)
