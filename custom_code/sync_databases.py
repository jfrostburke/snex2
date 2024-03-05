#!/usr/bin/env python

from sqlalchemy import create_engine, and_, update, insert, pool, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base
from sqlalchemy.sql import func

import json
from contextlib import contextmanager
import os
import datetime
from django.conf import settings

_SNEX2_DB = 'postgresql://{}:{}@supernova.science.lco.global:5435/snex2'.format(os.environ.get('SNEX2_DB_USER'), os.environ.get('SNEX2_DB_PASSWORD'))

engine1 = create_engine(settings.SNEX1_DB_URL)
engine2 = create_engine(_SNEX2_DB)

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
    Base.prepare(autoload_with=engine)

    table = getattr(Base.classes, tablename)
    return table


### Define our SNex1 db tables as Classes
Db_Changes = load_table('db_changes', db_address=settings.SNEX1_DB_URL)
Photlco = load_table('photlco', db_address=settings.SNEX1_DB_URL)
Spec = load_table('spec', db_address=settings.SNEX1_DB_URL)
Targets = load_table('targets', db_address=settings.SNEX1_DB_URL)
Target_Names = load_table('targetnames', db_address=settings.SNEX1_DB_URL)
Classifications = load_table('classifications', db_address=settings.SNEX1_DB_URL)
Groups = load_table('groups', db_address=settings.SNEX1_DB_URL)

### And our SNex2 tables
Datum = load_table('tom_dataproducts_reduceddatum', db_address=_SNEX2_DB)
Target = load_table('tom_targets_target', db_address=_SNEX2_DB)
Target_Extra = load_table('tom_targets_targetextra', db_address=_SNEX2_DB)
Targetname = load_table('tom_targets_targetname', db_address=_SNEX2_DB)
Auth_Group = load_table('auth_group', db_address=_SNEX2_DB)
Group_Perm = load_table('guardian_groupobjectpermission', db_address=_SNEX2_DB)
Datum_Extra = load_table('custom_code_reduceddatumextra', db_address=_SNEX2_DB)

### Make a dictionary of the groups in the SNex1 db
with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
    snex1_groups = {}
    for x in db_session.query(Groups):
        snex1_groups[x.name] = x.idcode
    

def query_db_changes(table, action, db_address=settings.SNEX1_DB_URL):
    """
    Query the db_changes table

    Parameters
    ----------
    table: str, table that was modified
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the database containing table
    """
    #table_dict = {'photlco': Photlco, 'spec': Spec, 'targets': Targets, 'targetnames': Target_Names}
    with get_session(db_address=db_address) as db_session:
        criteria = and_(Db_Changes.tablename==table, Db_Changes.action==action)
        record = db_session.query(Db_Changes).filter(criteria)#.order_by(Db_Changes.id.desc()).all()
    return record


def get_current_row(table, id_, db_address=settings.SNEX1_DB_URL):
    """ 
    Get the row that was modified, as recorded in the db_changes table
    
    Parameters
    ----------
    table: Table, the table in the SNex1 db that was modified, i.e. Photlco
    id_: int, the id of the modified row
    db_address: str, sqlalchemy address to the database containing table
    """
    with get_session(db_address=db_address) as db_session:
        criteria = getattr(table, 'id') == id_
        record = db_session.query(table).filter(criteria).first()
    return record


def delete_row(table, id_, db_address=settings.SNEX1_DB_URL):
    """
    Deletes a given row in table
    
    Parameters
    ----------
    table: Table, the table to clear
    id_: int, id of row to delete
    db_address: str, sqlalchemy address to the db_changes table
    """
    with get_session(db_address=db_address) as db_session:
        criteria = getattr(table, 'id') == id_
        db_session.query(table).filter(criteria).delete()
        db_session.commit()

def update_permissions(groupid, permissionid, objectid, contentid):
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
    
    with get_session(db_address=_SNEX2_DB) as db_session:
        for g_name, g_id in snex1_groups.items():
            if g_id in target_groups:
                snex2_groupid = db_session.query(Auth_Group).filter(Auth_Group.name==g_name).first().id
                update_permission = db_session.add(Group_Perm(object_pk=str(objectid), content_type_id=contentid, group_id = snex2_groupid, permission_id = permissionid))
    db_session.commit()


def update_phot(action, db_address=_SNEX2_DB):
    """
    Queries the ReducedDatum table in the SNex2 db with any changes made to the Photlco table in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    phot_result = query_db_changes('photlco', action, db_address=settings.SNEX1_DB_URL)
    for result in phot_result:
        try:
            id_ = result.rowid # The ID of the row in the photlco table
            phot_row = get_current_row(Photlco, id_, db_address=settings.SNEX1_DB_URL) # The row corresponding to id_ in the photlco table    
            #targetid = phot_row.targetid
            
            if action=='delete':
                #Look up the dataproductid from the datum_extra table
                with get_session(db_address=db_address) as db_session:
                    
                    #snex2_id_query = db_session.query(Datum).filter(and_(Datum.target_id==targetid, Datum.data_type=='photometry')).all()
                    snex2_id_query = db_session.query(Datum).filter(Datum.data_type=='photometry').order_by(Datum.id.desc()).all()
                    for snex2_row in snex2_id_query:
                        value = snex2_row.value
                        if type(value) == str:
                            value = json.loads(snex2_row.value)
                        if id_ == value.get('snex_id', ''):
                            db_session.delete(snex2_row)
                            break
                    db_session.commit()

                    #snex2_id_query = db_session.query(Datum_Extra).filter(and_(Datum_Extra.snex_id==id_, Datum_Extra.data_type=='photometry')).first()
                    #if snex2_id_query is not None: #Is none if row gets inserted and deleted in same 5 min block
                        #snex2_id = snex2_id_query.reduced_datum_id
                        #datum = db_session.query(Datum).filter(Datum.id==snex2_id).first()
                        #db_session.delete(datum)
                    #db_session.commit()

                #Delete all other rows corresponding to this dataproduct in the db_changes table
                with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
                    all_other_rows = db_session.query(Db_Changes).filter(and_(Db_Changes.tablename=='photlco', Db_Changes.rowid==id_))
                    for row in all_other_rows:
                        db_session.delete(row)
                    db_session.commit()
                    
            else:

                targetid = phot_row.targetid
                dobs = phot_row.dateobs
                tobs = phot_row.ut
                if tobs is None:
                    tobs = '00:00:00'
                if dobs is None:
                    dobs = datetime.datetime.today().strftime('%Y-%m-%d')
                time = '{} {}'.format(dobs, tobs) 
                
                if int(phot_row.mag) != 9999:
                    if int(phot_row.filetype) == 1:
                        phot = {'magnitude': float(phot_row.mag), 'filter': phot_row.filter, 'error': float(phot_row.dmag), 'snex_id': int(id_), 'background_subtracted': False, 'telescope': phot_row.telescope, 'instrument': phot_row.instrument}
                    elif int(phot_row.filetype) == 3 and phot_row.difftype is not None:
                        if int(phot_row.difftype) == 0:
                            subtraction_algorithm = 'Hotpants'
                        elif int(phot_row.difftype) == 1:
                            subtraction_algorithm = 'PyZOGY'
                        filename = phot_row.filename
                        if 'SDSS' in filename:
                            template_source = 'SDSS'
                        else:
                            template_source = 'LCO'
                        phot = {'magnitude': float(phot_row.mag), 'filter': phot_row.filter, 'error': float(phot_row.dmag), 'snex_id': int(id_), 'background_subtracted': True, 'subtraction_algorithm': subtraction_algorithm, 'template_source': template_source, 'reduction_type': 'manual', 'telescope': phot_row.telescope, 'instrument': phot_row.instrument}
                    
                    else:
                        phot = {'snex_id': int(id_)}
                else:
                    phot = {'snex_id': int(id_)}
    
                phot_groupid = phot_row.groupidcode
    
                with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
                    standard_list = db_session.query(Targets).filter(Targets.classificationid==1)
                    standard_ids = [x.id for x in standard_list]
                if targetid not in standard_ids and int(phot_row.filetype) in (1,3):
                    with get_session(db_address=db_address) as db_session:
                        #criteria = and_(Datum.data_type=='photometry', Datum.timestamp==time)
                        if action=='update':
                            #snex2_id_query = db_session.query(Datum_Extra).filter(and_(Datum_Extra.snex_id==id_, Datum_Extra.data_type=='photometry')).first()
                            ##if snex2_id_query is not None:
                            #snex2_id = snex2_id_query.reduced_datum_id
                            
                            snex2_id_query = db_session.query(Datum).filter(and_(Datum.target_id==targetid, Datum.data_type=='photometry')).all()
                            for snex2_row in snex2_id_query:
                                value = snex2_row.value
                                if type(value) == str: #Some rows are still strings for some reason
                                    value = json.loads(snex2_row.value)
                                if int(id_) == value.get('snex_id', ''):
                                    snex2_id = snex2_row.id
                                    db_session.query(Datum).filter(Datum.id==snex2_id).update({'target_id': targetid, 'timestamp': time, 'value': phot, 'data_type': 'photometry', 'source_name': '', 'source_location': ''})
                                    break

                        elif action=='insert':
                            newphot = Datum(target_id=targetid, timestamp=time, value=phot, data_type='photometry', source_name='', source_location='')
                            db_session.add(newphot)
                            db_session.flush()
    
                            if phot_groupid is not None:
                                update_permissions(int(phot_groupid), 77, newphot.id, 19) #View reduceddatum

                            #newphot_extra = Datum_Extra(snex_id=int(id_), reduced_datum_id=int(newphot.id), data_type='photometry', key='filetype', value=phot_row.filetype, float_value = float(phot_row.filetype))
                            #db_session.add(newphot_extra)

                        db_session.commit()
                delete_row(Db_Changes, result.id, db_address=settings.SNEX1_DB_URL)

        except:
            raise #continue


def read_spec(filename):
    """
    Read an ascii spectrum file and return a JSON dump-s of the wavelengths and fluxes

    Parameters
    ----------
    filename: str, the filepath+filename of the ascii file to read
    """
    spec_file = open(filename, 'r')
    lines = [x.split() for x in spec_file.readlines()]
    data = {"{}".format(i): {"wavelength": float(lines[i][0]), "flux": float(lines[i][1])} for i in range(len(lines)) if lines[i][1] != 'nan'}
    return(data)


def update_spec(action, db_address=_SNEX2_DB):
    """
    Queries the ReducedDatum table in the SNex2 db with any changes made to the Spec table in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    spec_result = query_db_changes('spec', action, db_address=settings.SNEX1_DB_URL)
    for result in spec_result:
        try:
            id_ = result.rowid # The ID of the row in the spec table

            if action=='delete':
                #Look up the dataproductid from the datum_extra table
                with get_session(db_address=db_address) as db_session:
                    
                    #snex2_id_query = db_session.query(Datum).filter(and_(Datum.target_id==targetid, Datum.data_type=='spectroscopy')).all()
                    #for snex2_row in snex2_id_query:
                    #    value = json.loads(snex2_row.value)
                    #    if id_ == value.get('snex_id', ''):
                    #        db_session.delete(snex2_row)
                    #        break
                    #db_session.commit()

                    snex2_id_query = db_session.query(Datum_Extra).filter(and_(Datum_Extra.data_type=='spectroscopy', Datum_Extra.key=='snex_id')).all()
                    for snex2_row in snex2_id_query:
                        value = json.loads(snex2_row.value)
                        if id_ == value.get('snex_id', ''):
                            snex2_id = value.get('snex2_id', '')
                            db_session.query(Datum).filter(and_(Datum.data_type=='spectroscopy', Datum.id==snex2_id)).delete()
                            break
                    db_session.commit()

            else:
                spec_row = get_current_row(Spec, id_, db_address=settings.SNEX1_DB_URL) # The row corresponding to id_ in the spec table

                if not spec_row:
                    delete_row(Db_Changes, result.id, db_address=settings.SNEX1_DB_URL)
                    continue

                targetid = spec_row.targetid
                time = '{} {}'.format(spec_row.dateobs, spec_row.ut) 
                spec = read_spec(spec_row.filepath + spec_row.filename.replace('.fits', '.ascii'))
                spec_groupid = spec_row.groupidcode
    
                with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
                    standard_list = db_session.query(Targets).filter(Targets.classificationid==1)
                    standard_ids = [x.id for x in standard_list]
                if targetid not in standard_ids:
                    with get_session(db_address=db_address) as db_session:
                        #criteria = and_(Datum.data_type=='spectroscopy', Datum.timestamp==time)
                        if action=='update':
                            #snex2_id_query = db_session.query(Datum).filter(and_(Datum.target_id==targetid, Datum.data_type=='spectroscopy')).all()
                            #for snex2_row in snex2_id_query:
                            #    value = json.loads(snex2_row.value)
                            #    if id_ == value.get('snex_id', ''):
                            #        snex2_row.update({'target_id': targetid, 'timestamp': time, 'value': spec, 'data_type': 'spectroscopy', 'source_name': '', 'source_location': ''})
                            #        break
                            
                            snex2_id_query = db_session.query(Datum_Extra).filter(and_(Datum_Extra.target_id==targetid, Datum_Extra.key=='snex_id', Datum_Extra.data_type=='spectroscopy')).all()
                            for snex2_row in snex2_id_query:
                                value = json.loads(snex2_row.value)
                                if id_ == value.get('snex_id', ''):
                                    snex2_id = value.get('snex2_id', '')
                                    db_session.query(Datum).filter(Datum.id==snex2_id).update({'target_id': targetid, 'timestamp': time, 'value': spec, 'data_type': 'spectroscopy', 'source_name': '', 'source_location': ''})
                                    break

                        elif action=='insert':
                            newspec = Datum(target_id=targetid, timestamp=time, value=spec, data_type='spectroscopy', source_name='', source_location='')
                            db_session.add(newspec)
                            db_session.flush()

                            if spec_groupid is not None:
                                update_permissions(int(spec_groupid), 77, newspec.id, 19) #View reduceddatum
 
                            #newspec_extra = Datum_Extra(snex_id=int(id_), reduced_datum_id=int(newspec.id), data_type='spectroscopy', key='', value='')
                            #db_session.add(newspec_extra)

                            newspec_extra_value = json.dumps({'snex_id': int(id_), 'snex2_id': int(newspec.id)})
                            newspec_extra = Datum_Extra(target_id=targetid, data_type='spectroscopy', key='snex_id', value=newspec_extra_value)
                            db_session.add(newspec_extra)

                            spec_extras = {}
                            for key in ['telescope', 'instrument', 'exptime', 'slit', 'airmass', 'reducer']:
                                if getattr(spec_row, key):
                                    spec_extras[key] = getattr(spec_row, key)
                            spec_extras['snex_id'] = int(id_)
                            spec_extras_row = Datum_Extra(data_type='spectroscopy', key='spec_extras', value=json.dumps(spec_extras), target_id=targetid)
                            db_session.add(spec_extras_row)

                        db_session.commit()
            delete_row(Db_Changes, result.id, db_address=settings.SNEX1_DB_URL)

        except:
            raise #continue


def update_target(action, db_address=_SNEX2_DB):
    """
    Queries the Target table in the SNex2 db with any changes made to the Targets and Targetnames tables in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    target_result = query_db_changes('targets', action, db_address=settings.SNEX1_DB_URL)
    name_result = query_db_changes('targetnames', action, db_address=settings.SNEX1_DB_URL)

    for tresult in target_result:
        try:
            target_id = tresult.rowid # The ID of the row in the targets table
            target_row = get_current_row(Targets, target_id, db_address=settings.SNEX1_DB_URL) # The row corresponding to target_id in the targets table

            t_ra = target_row.ra0
            t_dec = target_row.dec0
            t_modified = target_row.lastmodified
            t_created = target_row.datecreated
            if t_created is None:
                t_created = t_modified
            t_groupid = int(target_row.groupidcode)

            ### Get the name of the target
            with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
                name_query = db_session.query(Target_Names).filter(Target_Names.targetid==target_row.id).first()
                t_name = name_query.name
                db_session.commit()

            with get_session(db_address=db_address) as db_session:
                criteria = getattr(Target, 'id') == target_id
                if action=='update':
                    db_session.query(Target).filter(criteria).update({'ra': t_ra, 'dec': t_dec, 'modified': t_modified, 'created': t_created, 'type': 'SIDEREAL', 'epoch': 2000, 'scheme': ''})

                elif action=='insert':
                    existing_target_query = db_session.query(Target).filter(criteria).first()
                    if not existing_target_query:
                        db_session.add(Target(id=target_id, name=t_name, ra=t_ra, dec=t_dec, modified=t_modified, created=t_created, type='SIDEREAL', epoch=2000, scheme=''))
                        if 'postgresql' in db_address:
                            db_session.execute(select(func.setval('tom_targets_target_id_seq', target_id)))
                        update_permissions(t_groupid, 47, target_id, 12) #Change target
                        update_permissions(t_groupid, 48, target_id, 12) #Delete target
                        update_permissions(t_groupid, 49, target_id, 12) #View target

                elif action=='delete':
                    db_session.query(Target).filter(criteria).delete()

                db_session.commit()
            #delete_row(Db_Changes, tresult.id, db_address=_SNEX1_DB)

        except:
            raise #continue

    for nresult in name_result:
        try:
            name_id = nresult.rowid # The ID of the row in the targetnames table
            name_row = get_current_row(Target_Names, name_id, db_address=settings.SNEX1_DB_URL) # The row corresponding to name_id in the targetnames table

            if action!='delete':
                n_id = name_row.targetid
                t_name = name_row.name

            with get_session(db_address=db_address) as db_session:
                targetname_criteria = and_(Targetname.name==t_name, Targetname.target_id==n_id)
                #targetname_criteria = Targetname.target_id == n_id # Update the row in the targetname table that has the same targetid as the targetid in the targetnames table
                if action=='update':
                    db_session.query(Target).filter(Target.id==n_id).update({'name': t_name})
                    db_session.query(Targetname).filter(targetname_criteria).update({'name': t_name})

                elif action=='insert':
                    existing_name = db_session.query(Targetname).filter(Targetname.name==t_name, Targetname.target_id==n_id).first()
                    if not existing_name:
                        db_session.add(Targetname(name=t_name, target_id=n_id, created=datetime.datetime.utcnow(), modified=datetime.datetime.utcnow()))

                #elif action=='delete': #Currently doesn't work, need to fix?
                #    name_delete = db_session.query(Targetname).filter(targetname_criteria).first()
                #    db_session.delete(name_delete)

                db_session.commit()
            delete_row(Db_Changes, nresult.id, db_address=settings.SNEX1_DB_URL)
        
        except:
            raise #continue


def update_target_extra(action, db_address=_SNEX2_DB):
    """
    Queries the Targetextra table in the SNex2 db with any changes made to the Targets table, along with info from the Classifications table, in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    target_result = query_db_changes('targets', action, db_address=settings.SNEX1_DB_URL)

    for tresult in target_result:
        try:
            target_id = tresult.rowid # The ID of the row in the targets table
            target_row = get_current_row(Targets, target_id, db_address=settings.SNEX1_DB_URL) # The row corresponding to target_id in the targets table

            #t_id = target_row.id
            value = target_row.redshift
            if value is not None:
                with get_session(db_address=db_address) as db_session:
                    z_criteria = and_(Target_Extra.target_id==target_id, Target_Extra.key=='redshift') # Criteria for updating the redshift info in the targetextra table
                    
                    if action=='update':
                        if db_session.query(Target_Extra).filter(z_criteria).first() is not None:
                            db_session.query(Target_Extra).filter(z_criteria).update({'value': str(value), 'float_value': float(value)})
                        else:
                            db_session.add(Target_Extra(target_id=target_id, key='redshift', value=str(value), float_value=float(value)))

                    #Don't think the below are necessary, but need to double check
                    #elif action=='insert':
                        #db_session.add(Target_Extra(target_id=target_id, key='redshift', value=str(value), float_value=float(value)))
                    
                    elif action=='delete':
                        db_session.query(Target_Extra).filter(z_criteria).delete()
                    db_session.commit()

            class_id = target_row.classificationid
            if class_id is not None:
                class_name = get_current_row(Classifications, class_id, db_address=settings.SNEX1_DB_URL).name # Get the classification from the classifications table based on the classification id in the targets table (wtf)
                with get_session(db_address=db_address) as db_session:
                    c_criteria = and_(Target_Extra.target_id==target_id, Target_Extra.key=='classification') # Criteria for updating the classification info in the targetextra table
                    if action=='update':
                        if db_session.query(Target_Extra).filter(c_criteria).first() is not None:
                            db_session.query(Target_Extra).filter(c_criteria).update({'value': class_name})
                        else:
                            db_session.add(Target_Extra(target_id=target_id, key='classification', value=class_name))

                    elif action=='insert':
                        db_session.add(Target_Extra(target_id=target_id, key='classification', value=class_name))

                    elif action=='delete':
                        db_session.query(Target_Extra).filter(c_criteria).delete()

                    db_session.commit()
            delete_row(Db_Changes, tresult.id, db_address=settings.SNEX1_DB_URL)

        except:
            raise #continue


def migrate_data():
    """
    Migrates all changes from the SNex1 db to the SNex2 db,
    and afterwards deletes all the rows in the db_changes table
    """
    actions = ['delete', 'insert', 'update']
    for action in actions:
        update_target(action, db_address=_SNEX2_DB)
        update_target_extra(action, db_address=_SNEX2_DB)
        update_phot(action, db_address=_SNEX2_DB)
        update_spec(action, db_address=_SNEX2_DB)

migrate_data()
