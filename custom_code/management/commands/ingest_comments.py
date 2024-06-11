#!usr/bin/env python

from sqlalchemy import create_engine, and_, or_, update, insert, pool, exists
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base

import json
from contextlib import contextmanager
import os
import datetime

from django.core.management.base import BaseCommand
from tom_observations.models import ObservationGroup
from tom_targets.models import Target
from django_comments.models import Comment
from custom_code.management.commands.ingest_observations import get_session, load_table, update_permissions, get_snex2_params
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from guardian.shortcuts import assign_perm
from custom_code.models import ReducedDatumExtra
from django.conf import settings


engine1 = create_engine(settings.SNEX1_DB_URL)

def get_comments(targetid, tablename, notes, users, days_ago):
    
    content_dict = {'targets': ContentType.objects.get(model='target').id,
                    'obsrequests': ContentType.objects.get(model='observationgroup').id,
                    'spec': ContentType.objects.get(model='reduceddatum').id}
    
    with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        if targetid == 'all':
            comments = db_session.query(notes).filter(and_(notes.tablename==tablename, notes.datecreated > days_ago))
        else:
            comments = db_session.query(notes).filter(and_(notes.targetid==targetid, notes.tablename==tablename, notes.datecreated > days_ago))
        for comment in comments:

            usr = db_session.query(users).filter(users.id==comment.userid).first()
            snex2_user = User.objects.get(username=usr.name)
            target_id = comment.targetid
            
            if tablename == 'targets':
                # Check if it already exists in SNEx2
                old_comment = Comment.objects.filter(object_pk=target_id, comment=comment.note, content_type_id=content_dict[tablename]).first()
                if old_comment:
                    continue
                newcomment = Comment(
                        object_pk=target_id,
                        user_name=snex2_user.username,
                        user_email=snex2_user.email,
                        comment=comment.note,
                        submit_date=comment.posttime,
                        is_public=True,
                        is_removed=False,
                        content_type_id=content_dict[tablename],
                        site_id=2, #TODO: Why?
                        user_id=snex2_user.id
                    )
                newcomment.save()
            
            elif tablename == 'obsrequests':
                # Need to get the observationgroup id given its name
                obsgroup = ObservationGroup.objects.filter(name=str(comment.tableid)) #TODO: Check if should be str or int
                if obsgroup.count() > 0:
                    newcomment = Comment(
                            object_pk=obsgroup.first().id,
                            user_name=snex2_user.username,
                            user_email=snex2_user.email,
                            comment=comment.note,
                            submit_date=comment.posttime,
                            is_public=True,
                            is_removed=False,
                            content_type_id=content_dict[tablename],
                            site_id=2, #TODO: Why?
                            user_id=snex2_user.id
                        )
                    newcomment.save()

            elif tablename == 'spec':
                # Need to get reduceddatum id from the reduceddatumextra table
                rdes = ReducedDatumExtra.objects.filter(data_type='spectroscopy', key='snex_id', target_id=int(comment.targetid))
                snex2_id = False
                for rde in rdes:
                    if int(comment.tableid) == json.loads(rde.value)['snex_id']:
                        snex2_id = json.loads(rde.value)['snex2_id']
                        break
                if snex2_id:
                    # Check if it already exists in SNEx2
                    old_comment = Comment.objects.filter(object_pk=snex2_id, comment=comment.note, content_type_id=content_dict[tablename]).first()
                    if old_comment:
                        continue
                    newcomment = Comment(
                            object_pk=snex2_id,
                            user_name=snex2_user.username,
                            user_email=snex2_user.email,
                            comment=comment.note,
                            submit_date=comment.posttime,
                            is_public=True,
                            is_removed=False,
                            content_type_id=content_dict[tablename],
                            site_id=2, #TODO: Why?
                            user_id=snex2_user.id
                        )
                    newcomment.save()
   
    print('Done ingesting comments for target {} and table {}'.format(targetid, tablename))


class Command(BaseCommand):

    help = 'Ingests comments on targets, observation sequences, and spectra from SNEx1 to SNEx2'

    def add_arguments(self, parser):
        parser.add_argument('--tablename', help='Ingest comments for this table')
        parser.add_argument('--targetid', help='Ingest comments only for this target')
        parser.add_argument('--days_ago', help='Ingest people interested/uninterested from this many days ago')

    def handle(self, *args, **options):
        
        notes = load_table('notes', db_address=settings.SNEX1_DB_URL)
        users = load_table('users', db_address=settings.SNEX1_DB_URL)

        if not options['days_ago']:
            days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=9999)
        
        else:
            days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=float(options['days_ago']))
        
        if options['targetid']:
            get_comments(options['targetid'], options['tablename'], notes, users, days_ago)

        else:
            targetids = [t.id for t in Target.objects.all()]
            for targetid in targetids:
                get_comments(targetid, options['tablename'], notes, users, days_ago)
