import os
import requests
import logging
from astropy.time import Time, TimezoneInfo
from tom_dataproducts.models import ReducedDatum
import json
from tom_targets.templatetags.targets_extras import target_extra_field
from requests_oauthlib import OAuth1
from astropy.coordinates import SkyCoord
from astropy import units as u

from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from contextlib import contextmanager

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


def _load_table(tablename, db_address):
    Base = automap_base()
    engine = create_engine(db_address, poolclass=pool.NullPool)
    Base.prepare(engine, reflect=True)

    table = getattr(Base.classes, tablename)
    return(table)
 

def target_post_save(target, created):
  def get(objectId):
    url = 'https://mars.lco.global/'
    request = {'queries':
      [
        {'objectId': objectId}
      ]
      }
  
    try:
      r = requests.post(url, json=request)
      results = r.json()['results'][0]['results']
      return results
    
    except Exception as e:
      return [None,'Error message : \n'+str(e)]
 
  logger.info('Target post save hook: %s created: %s', target, created)

  ztf_name = next((name for name in target.names if 'ZTF' in name), None)
  if ztf_name:
    alerts = get(ztf_name)

    filters = {1: 'g_ZTF', 2: 'r_ZTF', 3: 'i_ZTF'}
    for alert in alerts:
        if all([key in alert['candidate'] for key in ['jd', 'magpsf', 'fid', 'sigmapsf']]):
            jd = Time(alert['candidate']['jd'], format='jd', scale='utc')
            jd.to_datetime(timezone=TimezoneInfo())
            value = {
                'magnitude': alert['candidate']['magpsf'],
                'filter': filters[alert['candidate']['fid']],
                'error': alert['candidate']['sigmapsf']
            }
            rd, created = ReducedDatum.objects.get_or_create(
                timestamp=jd.to_datetime(timezone=TimezoneInfo()),
                value=value,
                source_name=target.name,
                source_location=alert['lco_id'],
                data_type='photometry',
                target=target)
            rd.save()

  gaia_name = next((name for name in target.names if 'Gaia' in name), None)
  if gaia_name:
    base_url = 'http://gsaweb.ast.cam.ac.uk/alerts/alert'
    lightcurve_url = f'{base_url}/{gaia_name}/lightcurve.csv'

    response = requests.get(lightcurve_url)
    data = response._content.decode('utf-8').split('\n')[2:-2]

    jd = [x.split(',')[1] for x in data]
    mag = [x.split(',')[2] for x in data]

    for i in reversed(range(len(mag))):
        try:
            datum_mag = float(mag[i])
            datum_jd = Time(float(jd[i]), format='jd', scale='utc')
            value = {
                'magnitude': datum_mag,
                'filter': 'G_Gaia',
                'error': 0 # for now
            }
            rd, created = ReducedDatum.objects.get_or_create(
                timestamp=datum_jd.to_datetime(timezone=TimezoneInfo()),
                value=value,
                source_name=target.name,
                source_location=lightcurve_url,
                data_type='photometry',
                target=target)
            rd.save()
        except:
            pass

  ### Craig custom code starts here:
  ### ----------------------------------
    _snex1_address = 'mysql://{}:{}@localhost:3306/supernova'.format(os.environ['SNEX1_DB_USER'], os.environ['SNEX1_DB_PASSWORD'])

    with _get_session(db_address=_snex1_address) as db_session:
        Targets = _load_table('targets', db_address=_snex1_address)
        Targetnames = _load_table('targetnames', db_address=_snex1_address)
        if created == True: 
            # Insert into SNex 1 db
            db_session.add(Targets(ra0=target__ra, dec0=target__dec, lastmodified=target__modified, datecreated=target__created))
            db_session.add(Targetnames(targetid=target__id, name=target__name, datecreated=target__created, lastmodified=target__modified))
        elif created == False:
            # Update in SNex 1 db
            db_session.query(Targets).filter(target__id==Targets__id).update({'ra0': target__ra, 'dec0': target__dec, 'lastmodified': target__modified, 'datecreated': target__created})
            db_session.add(Targetnames(targetid=target__id, name=target__name, datecreated=target__created, lastmodified=target__modified))
        db_session.commit()

def targetextra_post_save(targetextra, created):
    logger.info('targetextra post save hook: %s created: %s', targetextra, created)
    _snex1_address = 'mysql://{}:{}@localhost:3306/supernova'.format(os.environ['SNEX1_DB_USER'], os.environ['SNEX1_DB_PASSWORD'])

    with _get_session(db_address=_snex1_address) as db_session:
        Targets = _load_table('targets', db_address=_snex1_address)
        Classifications = _load_table('classifications', db_address=_snex1_address)

        if targetextra.key == 'classification': # Update the classification in the targets table in the SNex 1 db
            targetid = targetextra__target_id # Get the targetid of our saved entry
            classification = targetextra__value # Get the new classification
            classificationid = db_session.query(Classifications).filter(Classifications__name==classification).first().id # Get the corresponding id from the classifications table
            db_session.query(Targets).filter(Targets__id==targetid).update({'classificationid': classificationid}) # Update the classificationid in the targets table

        elif targetextra.key == 'redshift': # Now update the targets table with the redshift info
            db_session.query(Targets).filter(Targets__id==targetextra__target_id).update({'redshift': targetextra__float_value})
        db_session.commit()


def sync_observation_with_snex1(snex_id, params):

    _snex1_address = 'mysql://{}:{}@localhost:3306/supernova'.format(os.environ['SNEX1_DB_USER'], os.environ['SNEX1_DB_PASSWORD'])
    instrument_dict = {'2M0-FLOYDS-SCICAM': 'floyds',
                       '1M0-SCICAM-SINISTRO': 'sinistro',
                       '2M0-SCICAM-MUSCAT': 'muscat'}

    with _get_session(db_address=_snex1_address) as db_session:
        Obslog = _load_table('obslog', db_address=_snex1_address)
        
        filtlist = ['U', 'B', 'V', 'R', 'I', 'u', 'gp', 'rp', 'ip', 'zs', 'w']
        if params['observation_type'] == 'IMAGING':
            filters = ''
            exptimes = ''
            numexp = ''
            for filt in filtlist:
                filt_params = params.get(filt)
                if filt_params and filt_params[0]:
                    filters += filt + ','
                    exptimes += str(filt_params[0])
                    numexp += str(filt_params[1])
            slit = 9999

        else:
            filters = 'floyds'
            exptime = params['exposure_time']
            numexp = params['exposure_count']
            slit = 2.0

        #db_session.add(
        #        Obslog(
        #            user=2, #TODO: Check this
        #            targetid=params['target_id'],
        #            triggerjd=float(str_to_mjd(params['start'])),
        #            windowstart=float(str_to_mjd(params['start'])), #TODO: Fix the str_to_mjd
        #            windowend=float(str_to_mjd(params['start']) + params['cadence_frequency']),
        #            filters=filters,
        #            exptimes=exptimes,
        #            numexp=numexp,
        #            proposal=params['proposal'],
        #            site=params.get('site', 'any'), #TODO: Fix this
        #            instrument=instrument_dict[params['instrument_type']],
        #            sky=9999,
        #            seeing=9999,
        #            airmass=params['max_airmass'],
        #            slit=slit,
        #            priority=params['observation_mode'].lower(),
        #            ipp=params['ipp_value'],
        #            requestsid=snex_id
        #        )
        #)

        #db_session.commit()

    logger.info('Sync observation with SNEx1 hook: Observation for SNEx1 ID {} synced'.format(snex_id))
