import os
import requests
import logging
from astropy.time import Time, TimezoneInfo
from tom_dataproducts.models import ReducedDatum
import json
from tom_targets.templatetags.targets_extras import target_extra_field
from tom_targets.models import TargetExtra
from custom_code.management.commands.ingest_ztf_data import get_ztf_data
from requests_oauthlib import OAuth1
from astropy.coordinates import SkyCoord
from astropy import units as u
from datetime import datetime, date, timedelta
import numpy as np
from django.contrib.auth.models import User
from django.conf import settings

from sqlalchemy import create_engine, pool, and_, or_, not_
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from contextlib import contextmanager
from collections import OrderedDict

logger = logging.getLogger(__name__)

@contextmanager
def _get_session(db_address):
    Base = automap_base()
    engine = create_engine(db_address, poolclass=pool.NullPool)
    Base.metadata.bind = engine

    db_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = db_session()

    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()


def _return_session(db_address=settings.SNEX1_DB_URL):
    ### This one is not run within a with loop, must be closed manually
    Base = automap_base()
    engine = create_engine(db_address, poolclass=pool.NullPool)
    Base.metadata.bind = engine

    db_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = db_session()

    return session


def _load_table(tablename, db_address):
    Base = automap_base()
    engine = create_engine(db_address, poolclass=pool.NullPool)
    Base.prepare(engine, reflect=True)

    table = getattr(Base.classes, tablename)
    return(table)
 

def _str_to_timestamp(datestring):
    """
    Converts string to a timestamp compatible with MYSQL timestamp field
    """
    timestamp = datetime.strptime(datestring, '%Y-%m-%dT%H:%M:%S')
    return timestamp.strftime('%Y-%m-%d %H:%M:%S')


def _str_to_jd(datestring):
    """
    Converts string to JD compatible with MYSQL double field
    """
    newdatestring = _str_to_timestamp(datestring)
    return np.round(Time(newdatestring, format='iso', scale='utc').jd, 8)


def _get_tns_params(target):

    names = [target.name] + [t.name for t in target.aliases.all()]

    tns_name = False
    for name in names:
        if 'SN' in name[:3]:
            tns_name = name.replace(' ','').replace('SN', '')
            break
        elif 'AT' in name[:3]:
            tns_name = name.replace(' ','').replace('AT', '')
            break

    if not tns_name:
        return {'status': 'No TNS name'}

    api_key = os.environ['TNS_APIKEY']
    tns_id = os.environ['TNS_APIID']

    tns_url = 'https://www.wis-tns.org/api/get/object'
    json_list = [('objname',tns_name), ('objid',''), ('photometry','1'), ('spectra','0')]
    json_file = OrderedDict(json_list)

    try:
        response = requests.post(tns_url, headers={'User-Agent': 'tns_marker{"tns_id":'+str(tns_id)+', "type":"bot", "name":"SNEx_Bot1"}'}, data={'api_key': api_key, 'data': json.dumps(json_file)})

        parsed = json.loads(response.text, object_pairs_hook=OrderedDict)
        result = json.dumps(parsed, indent=4)

        result = json.loads(result)
        discoverydate = result['data']['reply']['discoverydate']
        discoverymag = result['data']['reply']['discoverymag']
        discoveryfilt = result['data']['reply']['discmagfilter']['name']


        nondets = {}
        dets = {}

        photometry = result['data']['reply']['photometry']
        for phot in photometry:
            remarks = phot['remarks']
            if 'Last non detection' in remarks:
                nondet_jd = phot['jd']
                nondet_filt = phot['filters']['name']
                nondet_limmag = phot['limflux']

                nondets[nondet_jd] = [nondet_filt, nondet_limmag]

            else:
                det_jd = phot['jd']
                det_filt = phot['filters']['name']
                det_mag = phot['flux']

                dets[det_jd] = [det_filt, det_mag]


        first_det = min(dets.keys())

        last_nondet = 0
        for nondet, phot in nondets.items():
            if nondet > last_nondet and nondet < first_det:
                last_nondet = nondet

        response_data = {'success': 'Completed',
                         'nondetection': '{} ({})'.format(date.strftime(Time(last_nondet, scale='utc', format='jd').datetime, "%m/%d/%Y"), round(last_nondet, 2)) if last_nondet > 0 else None,
                         'nondet_mag': nondets[last_nondet][1] if last_nondet > 0 else None,
                         'nondet_filt': nondets[last_nondet][0] if last_nondet > 0 else None,
                         'detection': '{} ({})'.format(date.strftime(Time(first_det, scale='utc', format='jd').datetime, "%m/%d/%Y"), round(first_det, 2)),
                         'det_mag': dets[first_det][1],
                         'det_filt': dets[first_det][0]}
    
    except:
        logger.warning('TNS parameter ingestion failed for target {}'.format(target))
        response_data = {'failure': 'Parameters not ingested'}

    return response_data


def target_post_save(target, created, group_names=None, wrapped_session=None):
 
    logger.info('Target post save hook: %s created: %s', target, created)
    
    if not created:
        ### Add the last nondetection and first detection from TNS, if it exists
        tns_results = _get_tns_params(target)
        if tns_results.get('success', ''):
            nondet_date = tns_results['nondetection'].split()[0]
            nondet_jd = tns_results['nondetection'].split()[1].replace('(', '').replace(')', '')
            nondet_value = json.dumps({
                'date': nondet_date,
                'jd': nondet_jd,
                'mag': tns_results['nondet_mag'],
                'filt': tns_results['nondet_filt'],
                'source': 'TNS'
            })
            
            old_params = TargetExtra.objects.filter(target=target, key='last_nondetection')
            for old_param in old_params:
                old_param.delete()
            
            te = TargetExtra(
                target=target,
                key='last_nondetection',
                value=nondet_value
            )
            te.save()

            det_date = tns_results['detection'].split()[0]
            det_jd = tns_results['detection'].split()[1].replace('(', '').replace(')', '')
            det_value = json.dumps({
                'date': det_date,
                'jd': det_jd,
                'mag': tns_results['det_mag'],
                'filt': tns_results['det_filt'],
                'source': 'TNS'
            })
            
            old_params = TargetExtra.objects.filter(target=target, key='first_detection')
            for old_param in old_params:
                old_param.delete()
            
            te = TargetExtra(
                target=target,
                key='first_detection',
                value=det_value
            )
            te.save()

        ### Ingest ZTF data, if a ZTF target
        get_ztf_data(target)
  
        ### Not currently functional
        #gaia_name = next((name for name in target.names if 'Gaia' in name), None)
        #if gaia_name:
        #    base_url = 'http://gsaweb.ast.cam.ac.uk/alerts/alert'
        #    lightcurve_url = f'{base_url}/{gaia_name}/lightcurve.csv'

        #    response = requests.get(lightcurve_url)
        #    data = response._content.decode('utf-8').split('\n')[2:-2]

        #    jd = [x.split(',')[1] for x in data]
        #    mag = [x.split(',')[2] for x in data]

        #    for i in reversed(range(len(mag))):
        #        try:
        #            datum_mag = float(mag[i])
        #            datum_jd = Time(float(jd[i]), format='jd', scale='utc')
        #            value = {
        #                'magnitude': datum_mag,
        #                'filter': 'G_Gaia',
        #                'error': 0 # for now
        #            }
        #            rd, created = ReducedDatum.objects.get_or_create(
        #                timestamp=datum_jd.to_datetime(timezone=TimezoneInfo()),
        #                value=value,
        #                source_name=target.name,
        #                source_location=lightcurve_url,
        #                data_type='photometry',
        #                target=target)
        #            rd.save()
        #        except:
        #            pass

    else:

        if wrapped_session:
            db_session = wrapped_session
    
        else:
            db_session = _return_session(settings.SNEX1_DB_URL)
    
        Targets = _load_table('targets', db_address=settings.SNEX1_DB_URL)
        Targetnames = _load_table('targetnames', db_address=settings.SNEX1_DB_URL)
        Groups = _load_table('groups', db_address=settings.SNEX1_DB_URL)
        # Insert into SNEx 1 db
        if group_names:
            groupidcode = 0
            for group_name in group_names:
                groupidcode += int(db_session.query(Groups).filter(Groups.name==group_name).first().idcode)
        else:
            groupidcode = 32769 #Default in SNEx1
        snex1_target = Targets(id=target.id, ra0=target.ra, dec0=target.dec, groupidcode=groupidcode, lastmodified=target.modified, datecreated=target.created)
        db_session.add(snex1_target)
        db_session.add(Targetnames(targetid=target.id, name=target.name, datecreated=target.created, lastmodified=target.modified))
    
        if not wrapped_session:
            try:
                db_session.commit()
            except:
                db_session.rollback()
            finally:
                db_session.close()
        
        else:
            db_session.flush()


def targetextra_post_save(targetextra, created):
    '''
    Hook to sync target classifications and redshifts
    with SNEx1
    '''
    if not settings.DEBUG:
        with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
            Targets = _load_table('targets', db_address=settings.SNEX1_DB_URL)
            Classifications = _load_table('classifications', db_address=settings.SNEX1_DB_URL)

            if targetextra.key == 'classification': # Update the classification in the targets table in the SNex 1 db
                targetid = targetextra.target_id # Get the targetid of our saved entry
                classification = targetextra.value # Get the new classification
                classification_query = db_session.query(Classifications).filter(Classifications.name==classification).first()
                if classification_query:
                    # Get the corresponding id from the classifications table
                    classificationid = classification_query.id
                    db_session.query(Targets).filter(Targets.id==targetid).update({'classificationid': classificationid}) # Update the classificationid in the targets table

            elif targetextra.key == 'redshift': # Now update the targets table with the redshift info
                db_session.query(Targets).filter(Targets.id==targetextra.target_id).update({'redshift': targetextra.float_value})
            db_session.commit()
    logger.info('targetextra post save hook: %s created: %s', targetextra, created)


def targetname_post_save(targetname, created):
    '''
    Hook to sync target name with SNEx1
    '''
    if not settings.DEBUG:
        with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
            Names = _load_table('targetnames', db_address=settings.SNEX1_DB_URL)

            targetid = int(targetname.target_id) # Get the targetid of our saved entry
            name = targetname.name 
            if created:
               db_session.add(Names(targetid=targetid, name=name, datecreated=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')))
               db_session.commit()
    logger.info('targetname post save hook: %s created: %s', targetname, created)


def sync_observation_with_snex1(snex_id, params, requestgroup_id, wrapped_session=None):
    '''
    Hook to sync an obervation record submitted through SNEx2
    to the obslog table in the SNEx1 database
    '''
    instrument_dict = {'2M0-FLOYDS-SCICAM': 'floyds',
                       '1M0-SCICAM-SINISTRO': 'sinistro',
                       '2M0-SCICAM-MUSCAT': 'muscat'}

    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(settings.SNEX1_DB_URL)

    #with _get_session(db_address=_snex1_address) as db_session:
    Obslog = _load_table('obslog', db_address=settings.SNEX1_DB_URL)
    
    filtlist = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
    if params['observation_type'] == 'IMAGING':
        filters = ''
        exptimes = ''
        numexp = ''
        for filt in filtlist:
            filt_params = params.get(filt)
            if filt_params and filt_params[0]:
                if filters:
                    filters += ',' + filt[0]
                else:
                    filters += filt[0]
                
                if exptimes:
                    exptimes += ',' + str(int(filt_params[0]))
                else:
                    exptimes += str(int(filt_params[0]))
                
                if numexp:
                    numexp += ',' + str(filt_params[1])
                else:
                    numexp += str(filt_params[1])
        slit = 9999

    else:
        filters = 'floyds'
        exptimes = params['exposure_time']
        numexp = params['exposure_count']
        slit = 2.0
    
    if params.get('cadence_strategy'):
        window = min(float(params.get('cadence_frequency')), 1)
    else:
        window = float(params.get('cadence_frequency'))

    db_session.add(
            Obslog(
                user=67,
                targetid=params['target_id'],
                triggerjd=_str_to_jd(params['start']),
                windowstart=_str_to_jd(params['start']),
                windowend=_str_to_jd(params['start']) + window,
                filters=filters,
                exptime=exptimes,
                numexp=numexp,
                proposal=params['proposal'],
                site=params.get('site', 'any'),
                instrument=instrument_dict[params['instrument_type']],
                sky=9999,
                seeing=9999,
                airmass=params['max_airmass'],
                slit=slit,
                priority=params['observation_mode'].lower().replace(' ', '_'),
                ipp=params['ipp_value'],
                requestsid=snex_id,
                tracknumber=requestgroup_id
            )
    )

    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()

    else:
        db_session.flush()

    logger.info('Sync observation request with SNEx1 hook: Observation for SNEx1 ID {} synced'.format(snex_id))


def sync_sequence_with_snex1(params, group_names, userid=67, comment=False, targetid=None, wrapped_session=None):
    '''
    Hook to sync an observation sequence submitted through SNEx2 
    to the obsrequests table in the SNEx1 database
    '''

    instrument_dict = {'2M0-FLOYDS-SCICAM': 'floyds',
                       '1M0-SCICAM-SINISTRO': 'sinistro',
                       '2M0-SCICAM-MUSCAT': 'muscat',
                       '0M4-SCICAM-SBIG': 'sbig0m4'}

    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(settings.SNEX1_DB_URL)

    #with _get_session(db_address=_snex1_address) as db_session:
    Obsrequests = _load_table('obsrequests', db_address=settings.SNEX1_DB_URL)
    Groups = _load_table('groups', db_address=settings.SNEX1_DB_URL)
    Notes = _load_table('notes', db_address=settings.SNEX1_DB_URL)
    Users = _load_table('users', db_address=settings.SNEX1_DB_URL)

    # Get the idcodes from the groups in the group_list
    groupidcode = 0
    for group_name in group_names:
        groupidcode += int(db_session.query(Groups).filter(Groups.name==group_name).first().idcode)

    filtlist = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
    if params['observation_type'] == 'IMAGING':
        filters = ''
        exptimes = ''
        expnums = ''
        blocknums = ''
        for filt in filtlist:
            filt_params = params.get(filt)
            if filt_params and filt_params[0]:
                if filters:
                    filters += ',' + filt[0]
                else:
                    filters += filt[0]
                
                if exptimes:
                    exptimes += ',' + str(int(filt_params[0]))
                else:
                    exptimes += str(int(filt_params[0]))
                
                if expnums:
                    expnums += ',' + str(filt_params[1])
                else:
                    expnums += str(filt_params[1])

                if blocknums:
                    blocknums += ',' + str(filt_params[2])
                else:
                    blocknums += str(filt_params[2])
        slit = 9999

    else:
        filters = 'none'
        exptimes = params['exposure_time']
        expnums = params['exposure_count']
        blocknums = '1'
        slit = 2

    if params.get('cadence_strategy') == 'SnexResumeCadenceAfterFailureStrategy':
        cadence = float(params.get('cadence_frequency'))
        autostop = 0
        window = min(cadence, 1)
    else:
        cadence = float(params.get('cadence_frequency', 1.0))
        autostop = 1
        window = float(params.get('cadence_frequency', 1.0))

    if params.get('reminder'):
        nextreminder = _str_to_timestamp(params.get('reminder'))
    else:
        nextreminder = '0000-00-00 00:00:00'

    if userid != 67:
        try:
            # Get SNEx1 id corresponding to this user
            snex2_user = User.objects.get(id=userid)
            snex1_user = db_session.query(Users).filter(Users.name==snex2_user.username).first()
            snex1_userid = snex1_user.id
        except:
            snex1_userid = 67
    else:
        snex1_userid = 67
    
    newobsrequest = Obsrequests(
                targetid=params['target_id'],
                sequencestart=_str_to_timestamp(params['start']),
                sequenceend='0000-00-00 00:00:00',
                userstart=snex1_userid,
                cadence=cadence,
                window=window,
                filters=filters,
                exptimes=exptimes,
                expnums=expnums,
                blocknums=blocknums,
                proposalid=params['proposal'],
                ipp=params['ipp_value'],
                site=params.get('site', 'any'),
                instrument=instrument_dict[params['instrument_type']],
                airmass=float(params['max_airmass']),
                moondistlimit=float(params['min_lunar_distance']),
                slit=slit,
                acqradius=int(params.get('acquisition_radius', 0)),
                guidermode=params.get('guider_mode', '').upper(),
                guiderexptime=int(params.get('guider_exposure_time', 10)),
                priority=params['observation_mode'].lower().replace(' ', '_'),
                approved=1,
                nextreminder=nextreminder,
                groupidcode=groupidcode,
                dismissed=0,
                autostop=autostop,
                datecreated=_str_to_timestamp(params['start']),
                lastmodified=_str_to_timestamp(params['start'])
    )
    db_session.add(newobsrequest)

    db_session.flush()
    snex_id = newobsrequest.id
    
    if comment and targetid:
        newcomment = Notes(
                targetid=targetid,
                note=comment,
                tablename='obsrequests',
                tableid=snex_id,
                posttime=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'),
                userid=snex1_userid,
                datecreated=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
        )
        db_session.add(newcomment)

    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()

    else:
        db_session.flush()

    logger.info('Sync observation sequence with SNEx1 hook: Observation for SNEx1 ID {} synced'.format(snex_id))
    
    return snex_id


def cancel_sequence_in_snex1(snex_id, comment=False, tableid=None, userid=67, targetid=None, wrapped_session=None):
    '''
    Hook to cancel an observation sequence in SNEx1 
    that was canceled in SNEx2
    '''
    
    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(settings.SNEX1_DB_URL)
        
    #with _get_session(db_address=_snex1_address) as db_session:
    Obsrequests = _load_table('obsrequests', db_address=settings.SNEX1_DB_URL)
    Notes = _load_table('notes', db_address=settings.SNEX1_DB_URL)
    Users = _load_table('users', db_address=settings.SNEX1_DB_URL)

    if userid != 67:
        try:
            # Get SNEx1 id corresponding to this user
            snex2_user = User.objects.get(id=userid)
            snex1_user = db_session.query(Users).filter(Users.name==snex2_user.username).first()
            snex1_userid = snex1_user.id
        except:
            snex1_userid = 67
    else:
        snex1_userid = 67
    
    snex1_row = db_session.query(Obsrequests).filter(Obsrequests.id==snex_id).first()
    snex1_row.sequenceend = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    snex1_row.userend = snex1_userid

    if comment and tableid and targetid:
        newcomment = Notes(
                targetid=targetid,
                note=comment,
                tablename='obsrequests',
                tableid=tableid,
                posttime=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'),
                userid=snex1_userid,
                datecreated=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
        )
        db_session.add(newcomment)

    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()

    else:
        db_session.flush()

    logger.info('Cancel sequence in SNEx1 hook: Sequence with SNEx1 ID {} synced'.format(snex_id))


def approve_sequence_in_snex1(snex_id):
    '''
    Hook to approve a pending observation request in SNEx1 
    that was approved in SNEx2
    '''
    
    with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        Obsrequests = _load_table('obsrequests', db_address=settings.SNEX1_DB_URL)
 
        snex1_row = db_session.query(Obsrequests).filter(Obsrequests.id==snex_id).first()
        snex1_row.approved = 1
        snex1_row.lastmodified = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')

        db_session.commit()

    logger.info('Approve sequence in SNEx1 hook: Sequence with SNEx1 ID {} synced'.format(snex_id))


def update_reminder_in_snex1(snex_id, next_reminder, wrapped_session=None):
    '''
    Hook to update reminder for sequence in SNEx1.
    Runs after continuing a sequence from the scheduling page.
    '''

    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(settings.SNEX1_DB_URL)
    
    #with _get_session(db_address=_snex1_address) as db_session:
    Obsrequests = _load_table('obsrequests', db_address=settings.SNEX1_DB_URL)

    snex1_row = db_session.query(Obsrequests).filter(Obsrequests.id==snex_id).first()
    now = datetime.now()
    snex1_row.nextreminder = datetime.strftime(now + timedelta(days=next_reminder), '%Y-%m-%d %H:%M:%S')
 
    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()

    else:
        db_session.flush()

    logger.info('Update reminder in SNEx1 hook: Sequence with SNEx1 ID {} synced'.format(snex_id))


def find_images_from_snex1(targetid, allimages=False):
    '''
    Hook to find filenames of images in SNEx1,
    given a target ID
    '''
    
    with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        Photlco = _load_table('photlco', db_address=settings.SNEX1_DB_URL)

        if not allimages:
            query = db_session.query(Photlco).filter(and_(Photlco.targetid==targetid, Photlco.filetype==1)).order_by(Photlco.id.desc()).limit(8)
        else:
            query = db_session.query(Photlco).filter(and_(Photlco.targetid==targetid, Photlco.filetype==1)).order_by(Photlco.id.desc())
        filepaths = [q.filepath.replace('/supernova/data/lsc/', '').replace('/supernova/data/', '') for q in query]
        filenames = [q.filename.replace('.fits', '') for q in query]
        dates = [date.strftime(q.dateobs, '%m/%d/%Y') for q in query]
        teles = [q.telescope[:3] for q in query]
        filters = [q.filter for q in query]
        exptimes = [str(round(float(q.exptime))) + 's' for q in query]
        psfxs = [int(round(q.psfx)) for q in query]
        psfys = [int(round(q.psfy)) for q in query]

    logger.info('Found file names for target {}'.format(targetid))

    return filepaths, filenames, dates, teles, filters, exptimes, psfxs, psfys


def change_interest_in_snex1(targetid, username, status):
    '''
    Hook to change the status of an interested person
    in SNEx1
    '''

    with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        Interests = _load_table('interests', db_address=settings.SNEX1_DB_URL)
        Users = _load_table('users', db_address=settings.SNEX1_DB_URL)

        snex1_user = db_session.query(Users).filter(Users.name==username).first()
        now = datetime.strftime(datetime.utcnow(), '%Y-%m-%d %H:%M:%S')

        if status == 'interested':
            oldinterest = db_session.query(Interests).filter(and_(Interests.userid==snex1_user.id, Interests.targetid==targetid)).first()
            
            if not oldinterest:
                newinterest = Interests(userid=snex1_user.id, 
                                        targetid=targetid, 
                                        interested=now)
                db_session.add(newinterest)
            
            else:
                oldinterest.interested = now

        elif status == 'uninterested':
            oldinterest = db_session.query(Interests).filter(and_(Interests.userid==snex1_user.id, Interests.targetid==targetid)).first()
            oldinterest.uninterested = now

        db_session.commit()
    
    logger.info('Synced {} interested in target {} with SNEx1'.format(username, targetid))


def sync_paper_with_snex1(paper):
    '''
    Hook to ingest a paper into SNEx1
    '''
    with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        papers = _load_table('papers', db_address=settings.SNEX1_DB_URL)

        status_dict = {'in prep': 'inprep',
                       'submitted': 'submitted',
                       'published': 'published'
                    }

        targetid = paper.target_id
        reference = paper.author_last_name + ' et al.'
        status = status_dict[paper.status]
        contents = paper.description
        datecreated = datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')

        newpaper = papers(targetid=targetid, reference=reference, status=status, contents=contents, datecreated=datecreated)
        db_session.add(newpaper)

        db_session.commit()
    
    logger.info('Synced paper {} with SNEx1'.format(paper.id))


def sync_comment_with_snex1(comment, tablename, userid, targetid, snex1_rowid, wrapped_session=None):
    '''
    Hook to sync an observation sequence submitted through SNEx2 
    to the obsrequests table in the SNEx1 database
    '''
    if wrapped_session:
        db_session = wrapped_session

    else:
        db_session = _return_session(settings.SNEX1_DB_URL)
        #with _get_session(db_address=_snex1_address) as db_session:
    Notes = _load_table('notes', db_address=settings.SNEX1_DB_URL)
    Users = _load_table('users', db_address=settings.SNEX1_DB_URL)
    
    if userid != 67:
        try:
            # Get SNEx1 id corresponding to this user
            snex2_user = User.objects.get(id=userid)
            snex1_user = db_session.query(Users).filter(Users.name==snex2_user.username).first()
            snex1_userid = snex1_user.id
        except:
            snex1_userid = 67
    else:
        snex1_userid = 67
 
    existing_comment = db_session.query(Notes).filter(and_(Notes.targetid==targetid, Notes.note==comment, Notes.tablename==tablename, Notes.tableid==snex1_rowid)).first()
    if not existing_comment:
        newcomment = Notes(
                targetid=targetid,
                note=comment,
                tablename=tablename,
                tableid=snex1_rowid,
                posttime=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S'),
                userid=snex1_userid,
                datecreated=datetime.strftime(datetime.now(), '%Y-%m-%d %H:%M:%S')
        )
        db_session.add(newcomment)
    
    if not wrapped_session:
        try:
            db_session.commit()
        except:
            db_session.rollback()
        finally:
            db_session.close()
    
    else:
        db_session.flush()

    logger.info('Synced comment for table {} from user {}'.format(tablename, userid)) 


def get_unreduced_spectra(allspec=True):
    '''
    Hook to find unreduced spectra for FLOYDS inbox
    '''
    token = os.environ['LCO_APIKEY']

    response = requests.get('https://observe.lco.global/api/proposals?active=True&limit=50/',
                             headers={'Authorization': 'Token ' + token}).json()

    proposals = [prop['id'] for prop in response['results']]
    
    with _get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        speclcoraw = _load_table('speclcoraw', db_address=settings.SNEX1_DB_URL)
        targetnames = _load_table('targetnames', db_address=settings.SNEX1_DB_URL)
        targets = _load_table('targets', db_address=settings.SNEX1_DB_URL)
        classifications = _load_table('classifications', db_address=settings.SNEX1_DB_URL)
        spec = _load_table('spec', db_address=settings.SNEX1_DB_URL)

        original_filenames = [s.original for s in db_session.query(spec).filter(and_(spec.original!='None', spec.original!=None))]

        unreduced_spectra = db_session.query(speclcoraw).join(
                targets, speclcoraw.targetid==targets.id
        ).join(
                targetnames, speclcoraw.targetid==targetnames.targetid
        ).join(
                classifications, targets.classificationid==classifications.id, isouter=True
        ).filter(
            and_(
                not_(speclcoraw.filename.in_(original_filenames)), 
                speclcoraw.propid.in_(proposals),
                speclcoraw.filename.contains('e00.fits'),
                or_(
                    classifications.name != 'Standard', 
                    classifications.name == None
                ), 
                or_(
                    and_(
                        speclcoraw.type != 'LAMPFLAT', 
                        speclcoraw.type != 'ARC'
                    ), 
                speclcoraw.type == None
            ), 
            not_(speclcoraw.filepath.contains('bad')), 
            not_(targetnames.name.contains('test_'))
            )
        )
        targetids = [s.targetid for s in unreduced_spectra]
        propids = [s.propid for s in unreduced_spectra]
        dateobs = [s.dateobs for s in unreduced_spectra]
        paths = [s.filepath for s in unreduced_spectra]
        filenames = [s.filename for s in unreduced_spectra]
        imgpaths = [s.filepath.replace('/supernova/data/floyds', '/snex2/data/floyds') + s.filename.replace('.fits', '.png') for s in unreduced_spectra]

    return targetids, propids, dateobs, paths, filenames, imgpaths
