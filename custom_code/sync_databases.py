#!/usr/bin/env python

from sqlalchemy import create_engine, and_, update, insert, pool
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base

import json
from contextlib import contextmanager
import os
import datetime

_SNEX1_DB = 'mysql://{}:{}@localhost:3306/supernova?charset=utf8&use_unicode=1'.format(os.environ['SNEX1_DB_USER'], os.environ['SNEX1_DB_PASSWORD'])
_SNEX2_DB = 'postgresql://{}:{}@localhost:5435/snex2'.format(os.environ['SNEX2_DB_USER'], os.environ['SNEX2_DB_PASSWORD'])


@contextmanager
def get_session(db_address=_SNEX1_DB):
    """
    Get a connection to a database

    Returns
    ----------
    session: SQLAlchemy database session
    """
    Base = automap_base()
    engine = create_engine(db_address)
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


### Define our SNex1 db tables as Classes
Db_Changes = load_table('db_changes', db_address=_SNEX1_DB)
Photlco = load_table('photlco', db_address=_SNEX1_DB)
Spec = load_table('spec', db_address=_SNEX1_DB)
Targets = load_table('targets', db_address=_SNEX1_DB)
Target_Names = load_table('targetnames', db_address=_SNEX1_DB)
Classifications = load_table('classifications', db_address=_SNEX1_DB)

### And our SNex2 tables
Datum = load_table('tom_dataproducts_reduceddatum', db_address=_SNEX2_DB)
Target = load_table('tom_targets_target', db_address=_SNEX2_DB)
Target_Extra = load_table('tom_targets_targetextra', db_address=_SNEX2_DB)
Targetname = load_table('tom_targets_targetname', db_address=_SNEX2_DB)


def query_db_changes(table, action, db_address=_SNEX1_DB):
    """
    Query the db_changes table

    Parameters
    ----------
    table: str, table that was modified
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the database containing table
    """
    with get_session(db_address=db_address) as db_session:
        criteria = and_(Db_Changes.tablename==table, Db_Changes.action==action)
        record = db_session.query(Db_Changes).filter(criteria).order_by(table.id.desc()).all()
    return record


def get_current_row(table, id_, db_address=_SNEX1_DB):
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
        record = db_session.query(table).filter(criteria)
    return record


def delete_row(table, id_, db_address=_SNEX1_DB):
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


def update_phot(action, db_address=_SNEX2_DB):
    """
    Queries the ReducedDatum table in the SNex2 db with any changes made to the Photlco table in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    phot_result = query_db_changes('photlco', action, db_address=_SNEX1_DB)
    for result in phot_result:
        id_ = result.rowid # The ID of the row in the photlco table
        phot_row = get_current_row(Photlco, id_, db_address=_SNEX1_DB) # The row corresponding to id_ in the photlco table
        
        targetid = phot_row.targetid
        time = '{} {}'.format(phot_row.dateobs, phot_row.ut) 
        phot = json.dumps({'magnitude': float(phot_row.mag), 'filter': phot_row.filt, 'error': float(phot_row.dmag)})

        with get_session(db_address=db_address) as db_session:
            criteria = getattr(Datum, 'id') == id_
            if action=='update':
                db_session.query(Datum).filter(criteria).update({'target_id': targetid, 'timestamp': time, 'value': phot, 'data_type': 'photometry', 'source_name': '', 'source_location': ''})
            
            elif action=='insert':
                db_session.add(Datum(target_id=targetid, timestamp=time, value=phot, data_type='photometry', source_name='', source_location=''))
            
            elif action=='delete':
                db_session.query(Datum).filter(criteria).delete()

            db_session.commit()
        delete_row(Db_Changes, result.id, db_address=_SNEX1_DB)


def read_spec(filename):
    """
    Read an ascii spectrum file and return a JSON dump-s of the wavelengths and fluxes

    Parameters
    ----------
    filename: str, the filepath+filename of the ascii file to read
    """
    spec_file = open(filename, 'r')
    lines = [x.split() for x in spec_file.readlines()]
    data = {"{}".format(i): {"wavelength": float(lines[i][0]), "flux": float(lines[i][1])} for i in range(len(lines))}
    return(json.dumps(data))


def update_spec(action, db_address=_SNEX2_DB):
    """
    Queries the ReducedDatum table in the SNex2 db with any changes made to the Spec table in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    spec_result = query_db_changes('spec', action, db_address=_SNEX1_DB)
    for result in spec_result:
        id_ = result.rowid # The ID of the row in the spec table
        spec_row = get_current_row(Spec, id_, db_address=_SNEX1_DB) # The row corresponding to id_ in the spec table

        targetid = spec_row.targetid
        time = '{} {}'.format(spec_row.dateobs, spec_row.ut) 
        spec = read_spec(spec_row.filepath + spec_row.filename.replace('.fits', '.ascii'))

        with get_session(db_address=db_address) as db_session:
            criteria = getattr(Datum, 'id') == id_
            if action=='update':
                db_session.query(Datum).filter(criteria).update({'target_id': targetid, 'timestamp': time, 'value': spec, 'data_type': 'spectroscopy', 'source_name': '', 'source_location': ''})

            elif action=='insert':
                db_session.add(Datum(target_id=targetid, timestamp=time, value=spec, data_type='spectroscopy', source_name='', source_location=''))

            elif action=='delete':
                db_session.query(Datum).filter(criteria).delete()

            db_session.commit()
        delete_row(Db_Changes, result.id, db_address=_SNEX1_DB)


def update_target(action, db_address=_SNEX2_DB):
    """
    Queries the Target table in the SNex2 db with any changes made to the Targets and Targetnames tables in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    target_result = query_db_changes('targets', action, db_address=_SNEX1_DB)
    name_result = query_db_changes('targetnames', action, db_address=_SNEX1_DB)

    for tresult in target_result:
        target_id = tresult.rowid # The ID of the row in the targets table
        target_row = get_current_row(Targets, target_id, db_address=_SNEX1_DB) # The row corresponding the target_id in the targets table

        t_ra = target_row.ra0
        t_dec = target_row.dec0
        t_modified = target_row.lastmodified
        t_created = target_row.datecreated

        with get_session(db_address=db_address) as db_session:
            criteria = getattr(Target, 'id') == target_id
            if action=='update':
                db_session.query(Target).filter(criteria).update({'ra': ra, 'dec': dec, 'modified': modified, 'created': created, 'type': 'SIDEREAL', 'epoch': 2000, 'scheme': ''})

            elif action=='insert':
                db_session.add(Target(ra=t_ra, dec=t_dec, modified=t_modified, created=t_created, type='SIDEREAL', epoch=2000, scheme=''))

            elif action=='delete':
                db_session.query(Target).filter(criteria).delete()

            db_session.commit()
        delete_row(Db_Changes, tresult.id, db_address=_SNEX1_DB)

    for nresult in name_result:
        name_id = nresult.rowid # The ID of the row in the targetnames table
        name_row = get_current_row(Target_Names, name_id, db_address=_SNEX1_DB) # The row corresponding to name_id in the targetnames table

        n_id = name_row.targetid
        t_name = name_row.name

        with get_session(db_address=db_address) as db_session:
            targetname_criteria = Targetname.target_id == n_id # Update the row in the targetname table that has the same targetid as the targetid in the targetnames table
            if action=='update':
                db_session.query(Target).filter(target_criteria).update({'name': name})
                db_session.query(Targetname).filter(targetname_criteria).update({'name': name})

            elif action=='insert':
                db_session.add(Targetname(name=t_name, target_id=n_id, created=datetime.datetime.utcnow(), modified=datetime.datetime.utcnow()))

            elif action=='delete':
                db_session.query(Targetname).filter(targetname_criteria).delete()

            db_session.commit()
        delete_row(Db_Changes, nresult.id, db_address=_SNEX1_DB)


def update_target_extra(action, db_address=_SNEX2_DB):
    """
    Queries the Targetextra table in the SNex2 db with any changes made to the Targets table, along with info from the Classifications table, in the SNex1 db

    Parameters
    ----------
    action: str, one of 'update', 'insert', or 'delete'
    db_address: str, sqlalchemy address to the SNex2 db
    """
    target_result = query_db_changes('targets', action, db_address=_SNEX1_DB)

    for tresult in target_result:
        target_id = tresult.rowid # The ID of the row in the targets table
        target_row = get_current_row(Targets, target_id, db_address=_SNEX1_DB) # The row corresponding to target_id in the targets table

        t_id = target_row.id
        value = target_row.redshift
        class_id = target_row.classificationid
        class_name = get_current_row(Classifications, class_id, db_address=_SNEX1_DB).name # Get the classification from the classifications table based on the classification id in the targets table (wtf)

        with get_session(db_address=db_address) as db_session:
            z_criteria = and_(Target_Extra.target_id==t_id, Target_Extra.key=='redshift') # Criteria for updating the redshift info in the targetextra table
            c_criteria = and_(Target_Extra.target_id==t_id, Target_Extra.key=='classification') # Criteria for updating the classification info in the targetextra table
            if action=='update':
                db_session.query(Target_Extra).filter(z_criteria).update({'value': str(value), 'float_value': float(value)})
                db_session.query(Target_Extra).filter(c_criteria).update({'value': class_name})

            elif action=='insert':
                db_session.add(Target_Extra(target_id=t_id, key='redshift', value=str(value), float_value=float(value)))
                db_session.add(Target_Extra(target_id=t_id, key='classification', value=class_name))

            elif action=='delete':
                db_session.query(Target_Extra).filter(z_criteria).delete()
                db_session.query(Target_Extra).filter(c_criteria).delete()

            db_session.commit()
        delete_row(Db_Changes, tresult.id, db_address=_SNEX1_DB)


def migrate_data():
    """
    Migrates all changes from the SNex1 db to the SNex2 db,
    and afterwards deletes all the rows in the db_changes table
    """
    actions = ['update', 'insert', 'delete']
    try:
        for action in actions:
            update_phot(action, db_address=_SNEX2_DB)
            update_spec(action, db_address=_SNEX2_DB)
            update_target(action, db_address=_SNEX2_DB)
            update_target_extra(action, db_address=_SNEX2_DB)

    except:
        raise
