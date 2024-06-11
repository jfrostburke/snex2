#!usr/bin/env python

from sqlalchemy import create_engine, and_, or_, update, insert, pool, exists
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base

import json
from contextlib import contextmanager
import os
import datetime
import requests
from decimal import Decimal
from astropy.time import Time

from django.core.management.base import BaseCommand
from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from tom_targets.models import Target
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm
from django.conf import settings


engine1 = create_engine(settings.SNEX1_DB_URL)

@contextmanager
def get_session(db_address=settings.SNEX1_DB_URL):
    """
    Get a connection to a database

    Returns
    ----------
    session: SQLAlchemy database session
    """
    Base = automap_base()
    if db_address==settings.SNEX1_DB_URL:
        Base.metadata.bind = engine1
        db_session = sessionmaker(bind=engine1, autoflush=False, expire_on_commit=False)

    session = db_session()

    try:
        yield session
        session.commit()

    except:
        session.rollback()
        raise

    finally:
        session.close()


def load_table(tablename, db_address=settings.SNEX1_DB_URL):
    """
    Load a table with its data from a database

    Parameters
    ----------
    tablename: str, the name of the table to load
    db_address: str, sqlalchemy address to the table being loaded

    Returns
    ----------
    table: sqlalchemy table object
    """
    Base = automap_base()
    engine = create_engine(db_address, poolclass=pool.NullPool)
    Base.prepare(engine, reflect=True)

    table = getattr(Base.classes, tablename)
    return table


def update_permissions(groupid, obs, snex1_groups):
    """
    Updates permissions of a specific group for a certain target
    or reduceddatum

    Parameters
    ----------
    groupid: int, corresponding to which groups in SNex1 have permissions for this object
    permissionid: int, the permission id in the SNex2 db for this permission
    objectid: int, the row id of the object
    contentid: int, the content id in the SNex2 db for this object
    """
    def powers_of_two(num):
        powers = []
        i = 1
        while i <= num:
            if i & num:
                powers.append(i)
            i <<= 1
        return powers
    
    target_groups = powers_of_two(groupid)

    for g_name, g_id in snex1_groups.items():
        if g_id in target_groups:
            snex2_group = Group.objects.filter(name=g_name).first()
            assign_perm('view_observationrecord', snex2_group, obs)


def get_snex2_params(obs, repeating=True):
    """
    Takes an observation from SNEx1 and formats its parameters in a 
    format readable by SNEx2
    """
    instrument_dict = {'floyds': '2M0-FLOYDS-SCICAM',
                       'sinistro': '1M0-SCICAM-SINISTRO',
                       'muscat': "2M0-SCICAM-MUSCAT",
                       'spectral': '2M0-SPECTRAL-AG',
                       'sbig': '0M4-SCICAM-SBIG',
                       'sbig0m4': '0M4-SCICAM-SBIG'}
    obs_type_dict = {'floyds': 'SPECTRA',
                     'sinistro': 'IMAGING',
                     'muscat': 'IMAGING',
                     'spectral': 'IMAGING',
                     'sbig': 'IMAGING',
                     'sbig0m4': 'IMAGING'}
    filt_dict = {'g': 'gp',
                 'r': 'rp',
                 'i': 'ip',
                 'z': 'zs'}
            
    obs_dict = obs.__dict__
    obs_dict.pop('_sa_instance_state')

    ### Get this dictionary into a form useable by snex2
    
    snex2_param = {'facility': 'LCO'}
    
    cadence = float(obs_dict.get('cadence', 0))
    if repeating:
        snex2_param['cadence_strategy'] = 'SnexResumeCadenceAfterFailureStrategy'    
    else:
        snex2_param['cadence_strategy'] = 'SnexRetryFailedObservationsStrategy'
    snex2_param['cadence_frequency'] = cadence
    
    snex2_param['ipp_value'] = float(obs_dict['ipp'])
    snex2_param['max_airmass'] = float(obs_dict['airmass'])
    snex2_param['target_id'] = int(obs_dict['targetid'])
    snex2_param['name'] = obs_dict['id']
    try:
        snex2_param['min_lunar_distance'] = float(obs_dict['moondistlimit'])
    except:
        snex2_param['min_lunar_distance'] = 20.0
    try:
        snex2_param['observation_mode'] = obs_dict['priority'].upper()
    except:
        snex2_param['observation_mode'] = 'NORMAL'
    try:
        snex2_param['reminder'] = obs_dict['nextreminder'].strftime('%Y-%m-%dT%H:%M:%S')
    except:
        snex2_param['reminder'] = '0000-00-00T00:00:00'
    snex2_param['proposal'] = obs_dict['proposalid']
    
    snex2_param['instrument_type'] = instrument_dict[obs_dict['instrument']]
    snex2_param['observation_type'] = obs_type_dict[obs_dict['instrument']]
    snex2_param['site'] = obs_dict['site']
    
    if obs_dict['instrument'] == 'floyds':
        snex2_param['exposure_count'] = int(obs_dict['expnums'])
        snex2_param['exposure_time'] = float(obs_dict['exptimes'])
        try:
            snex2_param['acquisition_radius'] = float(obs_dict['acqradius'])
        except:
            snex2_param['acquisition_radius'] = 0.0
        try:
            snex2_param['guider_mode'] = obs_dict['guidermode'].lower()
        except:
            snex2_param['guider_mode'] = 'on'
        try:
            snex2_param['guider_exposure_time'] = float(obs_dict['guiderexptime'])
        except:
            snex2_param['guider_exposure_time'] = 0.0
        snex2_param['filter'] = "slit_2.0as"
    
    else:
        current_filts = obs_dict['filters'].split(',')
        exptimes = obs_dict['exptimes'].split(',')
        expnums = obs_dict['expnums'].split(',')
        blocknums = obs_dict['blocknums'].split(',')

        for i in range(len(current_filts)):
            current_filt = current_filts[i]
            if current_filt in filt_dict.keys():
                current_filt = filt_dict[current_filt]
            snex2_param[current_filt] = [float(exptimes[i]), int(expnums[i]), int(blocknums[i])]
    
        if obs_dict['instrument'] == 'muscat':
            snex2_param['guider_mode'] = 'ON'
            snex2_param['exposure_mode'] = 'ASYNCHRONOUS'
            for filt in current_filts:
                snex2_param['diffuser_'+filt+'_position'] = 'out'

    snex2_param['start'] = obs_dict['sequencestart'].strftime('%Y-%m-%dT%H:%M:%S')
    if obs_dict['sequenceend']:
        snex2_param['end'] = obs_dict['sequenceend'].strftime('%Y-%m-%dT%H:%M:%S')
    else:
        snex2_param['end'] = '' 
    
    return snex2_param


def add_permissions_to_templates(target_id, existing_obs, snex1_groups, obsrequests):
    
    with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        all_sequences = db_session.query(obsrequests).filter(
            and_(
                obsrequests.approved==1,
                obsrequests.targetid==target_id
            )
        )

        obs_to_add = []
        for o in all_sequences:
            if int(o.id) in existing_obs:
                obs_to_add.append(o)

        for obs in obs_to_add:
            obsgroup = ObservationGroup.objects.filter(name=str(obs.id)).first()
            template = obsgroup.observation_records.filter(observation_id='template').first()

            if template:
                update_permissions(int(obs.groupidcode), template, snex1_groups)
                print('Added permissions to template for target {} and sequence {}'.format(target_id, obsgroup.name))


def make_templates_for_target(target_id, existing_obs, snex1_groups, obsrequests, obslog, users):

    with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        ### Get all the sequences
        
        all_sequences = db_session.query(obsrequests).filter(
            and_(
                obsrequests.approved==1,
                obsrequests.targetid==target_id
            )
        )
        
        #print('Got active sequences')
        
        ### Compare the currently active sequences with the ones already in SNEx2
        obs_to_add = []
        for o in all_sequences:
            if int(o.id) in existing_obs:
                obs_to_add.append(o)
        
        #print('Found {} sequences to check'.format(len(obs_to_add)))
 
        for obs in obs_to_add:

            facility = 'LCO'
            created = obs.datecreated
            modified = obs.lastmodified
            user_id = 2 #supernova user in snex2
            requestsid = int(obs.id)
            
            snex2_param = get_snex2_params(obs, repeating=False)
            
            ### Find existing ObservationGroup in SNEx2
            obsgroup = ObservationGroup.objects.filter(name=str(requestsid)).first()
            if obsgroup:
                # Check for template record, and create one if one doesn't exist
                template_record = obsgroup.observation_records.filter(observation_id='template').first()
                if not template_record:
                    snex2_param['sequence_start'] = str(obs.sequencestart).replace(' ', 'T')
                    snex2_param['sequence_end'] = str(obs.sequenceend).replace(' ', 'T')
                    snex2_param['start_user'] = db_session.query(users).filter(users.id==obs.userstart).first().firstname

                    template = ObservationRecord(facility='LCO', observation_id='template',
                                status='', created=created, modified=modified,
                                target_id=target_id, user_id=user_id, parameters=snex2_param)
                    template.save()
                    obsgroup.observation_records.add(template)
                    #print('Created template record')
        
        print('Done with templates for target {}'.format(target_id))


def get_sequences_for_target(target_id, existing_obs, snex1_groups, obsrequests, obslog):

    with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        ### Get all the sequences
        onetime_sequence = db_session.query(obsrequests).filter(
            and_(
                obsrequests.autostop==1,
                obsrequests.approved==1,
                obsrequests.targetid==target_id
            ) 
        )
        
        repeating_sequence = db_session.query(obsrequests).filter(
            and_(
                obsrequests.autostop==0,
                obsrequests.approved==1,
                obsrequests.targetid==target_id
            )
        )
        
        #print('Got active sequences')
        
        ### Compare the currently active sequences with the ones already in SNEx2
        ### to see which ones need to be added and which ones need the newest obs requests
        
        onetime_obs_to_add = []
        repeating_obs_to_add = []
        
        existing_onetime_obs = []
        existing_repeating_obs = []
         
        for o in onetime_sequence:
            if int(o.id) not in existing_obs:
                onetime_obs_to_add.append(o)
            else:
                existing_onetime_obs.append(o)
        
        for o in repeating_sequence:
            if int(o.id) not in existing_obs:
                repeating_obs_to_add.append(o)
            else:
                existing_repeating_obs.append(o)
    
        #print('Found {} sequences to check'.format(len(onetime_obs_to_add) + len(repeating_obs_to_add) + len(existing_onetime_obs) + len(existing_repeating_obs)))
 
        count = 0
        #print('Getting parameters for new sequences')
        for sequencelist in [onetime_obs_to_add, existing_onetime_obs, repeating_obs_to_add, existing_repeating_obs]:
        
            for obs in sequencelist:
            
                facility = 'LCO'
                created = obs.datecreated
                modified = obs.lastmodified
                user_id = 2 #supernova user in snex2
                requestsid = int(obs.id)
                
                if obs.sequenceend == '0000-00-00 00:00:00' or not obs.sequenceend or obs.sequenceend > datetime.datetime.utcnow():
                    active = True
                else:
                    active = False                

                if count < 2:
                    snex2_param = get_snex2_params(obs, repeating=False)
                else:
                    snex2_param = get_snex2_params(obs, repeating=True)
                
                ### Create new observation group and dynamic cadence, if it doesn't already exist
                if count == 0 or count == 2:
                    newobsgroup = ObservationGroup(name=str(requestsid), created=created, modified=modified)
                    newobsgroup.save()
        
                    cadence_strategy = snex2_param['cadence_strategy']
                    cadence_params = {'cadence_frequency': snex2_param['cadence_frequency']}
                    newcadence = DynamicCadence(cadence_strategy=cadence_strategy, cadence_parameters=cadence_params, active=active, created=created, modified=modified, observation_group_id=newobsgroup.id)
                    newcadence.save()
                    #print('Added cadence and observation group')
                
                ### Get observation id from observation portal API
                # Query API
                #print('Querying API for sequence with SNEx1 ID of {}'.format(requestsid))
                # Get observation portal requestgroup id from most recent obslog entry for this observation sequence
                tracknumber_query = db_session.query(obslog).filter(and_(obslog.requestsid==requestsid, obslog.tracknumber>0)).order_by(obslog.id.asc())
                tracknumber_count = tracknumber_query.count()
    
                if tracknumber_count == 0:
                    continue
                
                for record in tracknumber_query:
                    tracknumber = int(record.tracknumber)
    
                    # Get the observation portal observation id using this tracknumber 
                    headers = {'Authorization': 'Token {}'.format(os.environ['LCO_APIKEY'])}
                    response = requests.get('https://observe.lco.global/api/requestgroups/{}'.format(tracknumber), headers=headers)
                    if not response.json().get('requests'): #SNEx doesn't have permission for these obs
                        continue
                    result = response.json()['requests'][0]
                    observation_id = int(result['id'])
                    status = result['state']
                   
                    in_snex2 = bool(ObservationRecord.objects.filter(observation_id=str(observation_id)).count())
                    snex2_param['start'] = Time(record.windowstart, format='jd').to_value('isot')
                    snex2_param['end'] = Time(record.windowend, format='jd').to_value('isot') 
                    
                    #print('This request has API id {} with status {}'.format(observation_id, status))
                    #print('and with parameters {}'.format(snex2_param))
     
                    ### Add the new cadence, observation group, and observation record to the SNEx2 db
                    try:
                
                        ### Add the new observation record, if it exists in SNEx1 but not SNEx2
                        if tracknumber_count > 0 and observation_id > 0 and not in_snex2:
                            newobs = ObservationRecord(facility=facility, observation_id=str(observation_id), status=status,
                                               created=created, modified=modified, target_id=target_id,
                                               user_id=user_id, parameters=snex2_param)
                            newobs.save()
                        
                            obs_groupid = int(obs.groupidcode)
                            if obs_groupid is not None:
                                update_permissions(int(obs_groupid), newobs, snex1_groups) #View obs record
                        
                            ### Add observaton record to existing observation group or the one we just made
                            if count == 0 or count == 2:
                                #print('Adding to new observation group')
                                newobsgroup.observation_records.add(newobs)
                            else:
                                oldobsgroup = ObservationGroup.objects.filter(name=str(requestsid)).first()
                                oldobsgroup.observation_records.add(newobs)
                            #print('Added observation record')
                    except:
                        raise
    
            count += 1

    print('Done with target {}'.format(target_id))


class Command(BaseCommand):

    help = 'Syncs observation sequences and records from SNEx1 to SNEx2 for a given target'

    def add_arguments(self, parser):
        parser.add_argument('--target_id', help='Ingest data for this SNEx1 target ID')
        parser.add_argument('--template', action='store_true', help='Create template observation records?')
        parser.add_argument('--perms', action='store_true', help='Add permissions to existing templates')

    def handle(self, *args, **options):

        ### Define our db tables as Classes
        obsrequests = load_table('obsrequests', db_address=_SNEX1_DB)
        obslog = load_table('obslog', db_address=_SNEX1_DB)
        Groups = load_table('groups', db_address=_SNEX1_DB)
        users = load_table('users', db_address=_SNEX1_DB)
        
        print('Made tables')
    
        # Get the observation groups already in SNEx2
        existing_obs = []
        for o in ObservationGroup.objects.all():
            try:
                existing_obs.append(int(o.name))
            except: # Name not a SNEx1 ID, so not in SNEx1
                continue
        
        with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
            ### Make a dictionary of the groups in the SNex1 db
            snex1_groups = {}
            for x in db_session.query(Groups):
                snex1_groups[x.name] = x.idcode 
        if options['template'] and options['target_id']:
            make_templates_for_target(options['target_id'], existing_obs, snex1_groups, obsrequests, obslog, users)
        elif options['template']:
            targets_in_snex2 = [int(t.id) for t in Target.objects.all()]
            for target_id in targets_in_snex2:
                make_templates_for_target(target_id, existing_obs, snex1_groups, obsrequests, obslog, users)
        elif options['perms'] and options['target_id']:
            add_permissions_to_templates(options['target_id'], existing_obs, snex1_groups, obsrequests)
        elif options['perms']:
            targets_in_snex2 = [int(t.id) for t in Target.objects.all()]
            for target_id in targets_in_snex2:
                add_permissions_to_templates(target_id, existing_obs, snex1_groups, obsrequests)

        elif options['target_id']:
            get_sequences_for_target(options['target_id'], existing_obs, snex1_groups, obsrequests, obslog)
        
        else:
            targets_in_snex2 = [int(t.id) for t in Target.objects.all()]
            for target_id in targets_in_snex2:
                get_sequences_for_target(target_id, existing_obs, snex1_groups, obsrequests, obslog)

