#!usr/bin/env python

from django.core.management.base import BaseCommand
import logging

logger = logging.getLogger(__name__)

class Command(BaseCommand):

    help = 'Logs "Hello world!"'

    def handle(self, *args, **kwargs):
        logger.info('Hello world!')
