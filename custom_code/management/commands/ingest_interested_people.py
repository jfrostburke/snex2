#!usr/bin/env python

from sqlalchemy import create_engine, and_, or_, update, insert, pool, exists
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base

import json
from contextlib import contextmanager
import os
import datetime

from django.core.management.base import BaseCommand
from django_comments.models import Comment
from tom_targets.models import Target
from custom_code.management.commands.ingest_observations import get_session, load_table, update_permissions, get_snex2_params
from custom_code.models import InterestedPersons
from django.contrib.auth.models import User
from django.conf import settings


engine1 = create_engine(settings.SNEX1_DB_URL)


class Command(BaseCommand):

    help = 'Ingests interested people from SNEx1 to SNEx2'

    def add_arguments(self, parser):
        parser.add_argument('--days_ago', help='Ingest people interested/uninterested from this many days ago')

    def handle(self, *args, **options):

        interests = load_table('interests', db_address=settings.SNEX1_DB_URL)
        users = load_table('users', db_address=settings.SNEX1_DB_URL)
        if not options.get('days_ago'):
            print('could not find days ago, using default value of 1')
            dg = 1
        else:
            dg = int(options['days_ago'])
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=dg)

        with get_session(db_address=settings.SNEX1_DB_URL) as db_session:
        
            interested_people = db_session.query(interests).filter(or_(interests.interested > days_ago, interests.uninterested > days_ago))
            for interest in interested_people:

                usr = db_session.query(users).filter(users.id==interest.userid).first()
                snex2_user = User.objects.filter(username=usr.name).first()

                t = Target.objects.filter(id=interest.targetid).first()
                if not t:
                    # Target not in SNEx2, so don't worry about it
                    continue

                if not snex2_user:
                    # User not yet in SNEx2, should probably record this
                    print('WARNING: User {} not in SNEx2'.format(usr.name))
                    continue
                
                ### Handle cases for newly interested person, newly interested person who then
                ### marked themselves as uninterested, and old interested person who recently
                ### marked themselves as uninterested

                if not interest.uninterested:# == '0000-00-00 00:00:00': #Case 1
                    # Check if this is already in SNEx2 (marked as interested in SNEx2 first)
                    if not InterestedPersons.objects.filter(target=t, user=snex2_user).first():
                        # Add to Interested Persons table
                        newinterest = InterestedPersons(target=t, user=snex2_user)
                        newinterest.save()
                        print('Saved newly interested person {} for target {}'.format(snex2_user.id, t.id))

                elif interest.interested > days_ago and interest.uninterested > days_ago: #Case 2
                    # No need to do anything, since the person marked and then unmarked themselves
                    # as interested in the time since this script last ran, but double check
                    # just in case timedelta has changed between then and now
                    oldinterest = InterestedPersons.objects.filter(target=t, user=snex2_user).first()
                    if oldinterest:
                        oldinterest.delete()
                        print('Deleted old interested person {} for target {}'.format(snex2_user.id, t.id))
                    
                else: #Case 3
                    # Get the correct row in the Interested Persons table and delete it
                    oldinterest = InterestedPersons.objects.filter(target=t, user=snex2_user).first()
                    if oldinterest:
                        oldinterest.delete()
                        print('Deleted old interested person {} for target {}'.format(snex2_user.id, t.id))

        print('Done syncing interested people')

