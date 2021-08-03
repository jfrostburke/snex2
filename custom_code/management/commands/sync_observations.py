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

from django.core.management.base import BaseCommand
from tom_observations.models import ObservationRecord, ObservationGroup, DynamicCadence
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm


_SNEX1_DB = 'mysql://{}:{}@supernova.science.lco.global:3306/supernova?charset=utf8&use_unicode=1'.format(os.environ.get('SNEX1_DB_USER'), os.environ.get('SNEX1_DB_PASSWORD'))

engine1 = create_engine(_SNEX1_DB)

@contextmanager
def get_session(db_address=_SNEX1_DB):
    """
    Get a connection to a database

    Returns
    ----------
    session: SQLAlchemy database session
    """
    Base = automap_base()
    if db_address==_SNEX1_DB:
        Base.metadata.bind = engine1
        db_session = sessionmaker(bind=engine1, autoflush=False, expire_on_commit=False)
    else:
        Base.metadata.bind = engine2
        db_session = sessionmaker(bind=engine2, autoflush=False, expire_on_commit=False)

    session = db_session()

    try:
        yield session
        session.commit()

    except:
        session.rollback()
        raise

    finally:
        session.close()


def load_table(tablename, db_address=_SNEX1_DB):
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
                       'muscat': "2M0-SCICAM-MUSCAT"}
    obs_type_dict = {'floyds': 'SPECTRA',
                     'sinistro': 'IMAGING',
                     'muscat': 'IMAGING'}
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
    snex2_param['min_lunar_distance'] = float(obs_dict['moondistlimit'])
    snex2_param['observation_mode'] = obs_dict['priority'].upper()
    snex2_param['reminder'] = obs_dict['nextreminder'].strftime('%Y-%m-%dT%H:%M:%S')
    snex2_param['proposal'] = obs_dict['proposalid']
    
    snex2_param['instrument_type'] = instrument_dict[obs_dict['instrument']]
    snex2_param['observation_type'] = obs_type_dict[obs_dict['instrument']]
    snex2_param['site'] = obs_dict['site']
    
    if obs_dict['instrument'] == 'floyds':
        snex2_param['exposure_count'] = int(obs_dict['expnums'])
        snex2_param['exposure_time'] = float(obs_dict['exptimes'])
        snex2_param['acquisition_radius'] = float(obs_dict['acqradius'])
        snex2_param['guider_mode'] = obs_dict['guidermode'].lower()
        snex2_param['guider_exposure_time'] = float(obs_dict['guiderexptime'])
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


class Command(BaseCommand):

    help = 'Syncs active observation sequences and records from SNEx1 to SNEx2'

    def handle(self, *args, **options):

        ### Define our db tables as Classes
        obsrequests = load_table('obsrequests', db_address=_SNEX1_DB)
        obslog = load_table('obslog', db_address=_SNEX1_DB)
        Groups = load_table('groups', db_address=_SNEX1_DB)
        
        #print('Made tables')
        
        with get_session(db_address=_SNEX1_DB) as db_session:
            ### Make a dictionary of the groups in the SNex1 db
            snex1_groups = {}
            for x in db_session.query(Groups):
                snex1_groups[x.name] = x.idcode 
        
            ### Get all the currently active sequences
            onetime_sequence = db_session.query(obsrequests).filter(
                and_(
                    obsrequests.autostop==1,
                    obsrequests.approved==1,
                    obsrequests.proposalid=='KEY2020B-002',
                    or_(
                        obsrequests.sequenceend=='0000-00-00 00:00:00', 
                        obsrequests.sequenceend>datetime.datetime.utcnow()
                    )
                ) 
            )
            onetime_sequence_ids = [int(o.id) for o in onetime_sequence]
        
            repeating_sequence = db_session.query(obsrequests).filter(
                and_(
                    obsrequests.autostop==0,
                    obsrequests.approved==1,
                    obsrequests.proposalid=='KEY2020B-002',
                    or_(
                        obsrequests.sequenceend=='0000-00-00 00:00:00', 
                        obsrequests.sequenceend>datetime.datetime.utcnow()
                    )
                )
            )
            repeating_sequence_ids = [int(o.id) for o in repeating_sequence]
        
        #print('Got active sequences')
        
        ### Cancel the SNEx2 sequences that are no longer active in SNEx1
        snex2_active_cadences = DynamicCadence.objects.filter(active=True)
        for cadence in snex2_active_cadences:
            obsgroupid = int(cadence.observation_group_id)
            currentobsgroup = ObservationGroup.objects.filter(id=obsgroupid).first()
            try:
                snex1id = int(currentobsgroup.name)
            except: # Name not an integer, so not an observation group from SNEx1
                continue
            if snex1id not in onetime_sequence_ids and snex1id not in repeating_sequence_ids:
                #print('Going to cancel cadence {}'.format(cadence.id))
                cadence.active = False
                cadence.save()

        #print('Canceled inactive sequences')
        
        ### Compare the currently active sequences with the ones already in SNEx2
        ### to see which ones need to be added and which ones need the newest obs requests
        
        onetime_obs_to_add = []
        repeating_obs_to_add = []
        
        existing_onetime_obs = []
        existing_repeating_obs = []
        
        # Get the observation groups already in SNEx2
        existing_obs = [int(o.name) for o in ObservationGroup.objects.all() if isinstance(o.name, int)]
            
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
        
        #print('Found {} sequences to check'.format(len(onetime_obs_to_add) + len(repeating_obs_to_add)))
 
        count = 0
        #print('Getting parameters for new sequences')
        for sequencelist in [onetime_obs_to_add, existing_onetime_obs, repeating_obs_to_add, existing_repeating_obs]:
        
            for obs in sequencelist:
            
                facility = 'LCO'
                created = obs.datecreated
                modified = obs.lastmodified
                target_id = int(obs.targetid)
                user_id = 67 #supernova
         
                ### Get observation id from observation portal API
                # Query API
        
                requestsid = int(obs.id)
                #print('Querying API for sequence with SNEx1 ID of {}'.format(requestsid))
                with get_session(db_address=_SNEX1_DB) as db_session:
                    # Get observation portal requestgroup id from most recent obslog entry for this observation sequence
                    tracknumber_query = db_session.query(obslog).filter(and_(obslog.requestsid==requestsid, obslog.tracknumber>0)).order_by(obslog.id.desc())
                    tracknumber_count = tracknumber_query.count()
        
                    if tracknumber_count > 0:
                        tracknumber = int(tracknumber_query.first().tracknumber)
        
                        # Get the observation portal observation id using this tracknumber 
                        headers = {'Authorization': 'Token {}'.format(os.environ['LCO_APIKEY'])}
                        response = requests.get('https://observe.lco.global/api/requestgroups/{}'.format(tracknumber), headers=headers)
                        result = response.json()['requests'][0]
                        observation_id = int(result['id'])
                        status = result['state']
                      
                        #print('The most recent observation request for this sequence has API id {} with status {}'.format(observation_id, status))
                        #print('and with parameters {}'.format(snex2_param))
        
                    else:
                        #print('No requests have been submitted for this sequence yet')
                        observation_id = 0
                        
                    if count < 2:
                        snex2_param = get_snex2_params(obs, repeating=False)
                    else:
                        snex2_param = get_snex2_params(obs, repeating=True)
                
                if observation_id:
                    in_snex2 = bool(ObservationRecord.objects.filter(observation_id=str(observation_id)).count())
                    #print('Is this observation request in SNEx2? {}'.format(in_snex2))
                else:
                    in_snex2 = False
                ### Add the new cadence, observation group, and observation record to the SNEx2 db
                
                try:
                
                    ### Create new observation group and dynamic cadence, if it doesn't already exist
                    if count == 0 or count == 2:
                        newobsgroup = ObservationGroup(name=str(requestsid), created=created, modified=modified)
                        newobsgroup.save()
        
                        cadence_strategy = snex2_param['cadence_strategy']
                        cadence_params = {'cadence_frequency': snex2_param['cadence_frequency']}
                        newcadence = DynamicCadence(cadence_strategy=cadence_strategy, cadence_parameters=cadence_params, active=True, created=created, modified=modified, observation_group_id=newobsgroup.id)
                        newcadence.save()
                        #print('Added cadence and observation group')
                        
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