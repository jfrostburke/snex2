#!usr/bin/env python

from sqlalchemy import create_engine, and_, or_, update, insert, pool, exists
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base

from django.core.management.base import BaseCommand
import logging
import os
from contextlib import contextmanager

logger = logging.getLogger(__name__)


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


class Command(BaseCommand):

    help = 'Test script to query the SNEx1 database from inside docker'

    def handle(self, *args, **kwargs):
        targets = load_table('targets', db_address=_SNEX1_DB)

        with get_session(db_address=_SNEX1_DB) as db_session:
            target_count = db_session.query(targets).count()

        logger.info('Hello world!')
        logger.info('There are {} targets in SNEx1'.format(target_count))
