#!usr/bin/env python

from sqlalchemy import create_engine, and_, or_, update, insert, pool, exists
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.automap import automap_base

import json
from contextlib import contextmanager
import os
import datetime

from django.core.management.base import BaseCommand
from tom_targets.models import Target
from custom_code.management.commands.ingest_observations import get_session, load_table
from custom_code.models import Papers
from django.conf import settings

engine1 = create_engine(settings.SNEX1_DB_URL)


class Command(BaseCommand):

    help = 'Ingests and syncs papers from SNEx1 to SNEx2'

    def add_arguments(self, parser):
        parser.add_argument('--days_ago', help='Ingest people interested/uninterested from this many days ago')

    def handle(self, *args, **options):

        papers = load_table('papers', db_address=settings.SNEX1_DB_URL)

        if not options.get('days_ago'):
            print('could not find days ago, using default value of 1')
            dg = 1
        
        else:
            dg = int(options['days_ago'])
        days_ago = datetime.datetime.utcnow() - datetime.timedelta(days=dg)

        status_dict = {'inprep': 'in prep',
                       'submitted': 'submitted',
                       'published': 'published'}

        with get_session(db_address=settings.SNEX1_DB_URL) as db_session:

            papers_to_add = db_session.query(papers).filter(or_(papers.datecreated > days_ago, papers.lastmodified > days_ago))

            for paper_to_add in papers_to_add:

                target = Target.objects.get(id=paper_to_add.targetid)
                
                reference = paper_to_add.reference
                author_last_name = reference.replace('.','').split('et al')[0].split(',')[0].replace(' ','')
                
                if paper_to_add.datecreated > days_ago and paper_to_add.lastmodified > days_ago:
                    # Paper was just added, so ingest it into SNEx2  
                    # But first, check if it was added to SNEx2 originally
                    oldpaper = Papers.objects.filter(target=target, author_last_name=author_last_name).first()
                    if oldpaper:
                        continue

                    description = paper_to_add.contents
                    
                    status = status_dict[paper_to_add.status]
                    created = str(paper_to_add.datecreated)

                    newpaper = Papers(target=target, 
                                      author_last_name=author_last_name, 
                                      description=description, 
                                      status=status, 
                                      created=created)
                    newpaper.save()
                    newpaper.created = created #Need to do this again because it defaults to now
                    newpaper.save()
                    print('Added new paper with snex1 id {} and name {}'.format(paper_to_add.id, author_last_name))

                elif paper_to_add.lastmodified > days_ago:
                    # Paper already in SNEx2 but was recently changed, so change it
                    oldpaper = Papers.objects.filter(target=target, author_last_name=author_last_name).first()
                    if oldpaper:
                        oldpaper.description = paper_to_add.contents
                        oldpaper.status = status_dict[paper_to_add.status]
                        oldpaper.save()
                        print('Modified existing paper with snex1 id {}'.format(paper_to_add.id))
                    else:
                        print('WARNING: This paper is not in snex1: {}'.format(paper_to_add.id))

        print('Done syncing papers')
