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
from custom_code.management.commands.ingest_observations import get_session, load_table, update_permissions, get_snex2_params
from django.contrib.auth.models import Group
from guardian.shortcuts import assign_perm


_SNEX1_DB = 'mysql://{}:{}@supernova.science.lco.global:3306/supernova?charset=utf8&use_unicode=1'.format(os.environ.get('SNEX1_DB_USER'), os.environ.get('SNEX1_DB_PASSWORD'))

engine1 = create_engine(_SNEX1_DB)


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
                    # Get observation portal requestgroup id from most recent obslog entry for this observation sequence
                    tracknumber_query = db_session.query(obslog).filter(and_(obslog.requestsid==requestsid, obslog.tracknumber>0)).order_by(obslog.id.desc())
                    tracknumber_count = tracknumber_query.count()
        
                    if tracknumber_count > 0:
                        tracknumber = int(tracknumber_query.first().tracknumber)
        
                        # Get the observation portal observation id using this tracknumber 
                        headers = {'Authorization': 'Token {}'.format(os.environ['LCO_APIKEY'])}
                        response = requests.get('https://observe.lco.global/api/requestgroups/{}'.format(tracknumber), headers=headers)
                        if not response.json().get('requests'):
                            continue
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
