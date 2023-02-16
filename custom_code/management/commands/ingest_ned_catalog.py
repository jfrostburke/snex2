from custom_code.models import NEDLVSCatalog
from django.core.management.base import BaseCommand
from astropy.io import fits
from astropy.table import Table, Column
import numpy as np


class Command(BaseCommand):

    help = 'Ingests the NED LVS catalog into the database'

    def add_arguments(self, parser):
        parser.add_argument('--filename', help='Ingest catalog information from this file')


    def handle(self, *args, **options):

        filename = options['filename']

        h = fits.open(filename) #Catalog in a fits file

        t = Table(h[1].data) #Load as astropy Table
        colnames = t.colnames

        # We're saving some values in JSONFields, so we want to get those colnames
        extinctionnames = []
        magnames = []
        lumnames = []
        sfrnames = []
        for name in colnames[:]:
            if 'A_' in name:
                extinctionnames.append(name)
                colnames.remove(name)
            elif 'Lum_' in name: # This one has to come before the next because 'm_' is in 'Lum_'
                lumnames.append(name)
                colnames.remove(name)
            elif 'm_' in name:
                magnames.append(name)
                colnames.remove(name)
            elif 'SFR_' in name:
                sfrnames.append(name)
                colnames.remove(name)
        
        newt = t[colnames] # Make a copy of the table without the columns that are going into dicts
        extt = t[extinctionnames] # Make separate tables for each set of dict values
        magt = t[magnames]
        lumt = t[lumnames]
        sfrt = t[sfrnames]

        # Make the dicts
        extdict = [dict(zip(extinctionnames, row)) for row in extt]
        magdict = [dict(zip(magnames, row)) for row in magt]
        lumdict = [dict(zip(lumnames, row)) for row in lumt]
        sfrdict = [dict(zip(sfrnames, row)) for row in sfrt]

        # Add these dicts back as columns in the new table
        extcol = Column(extdict, name='extinction')
        magcol = Column(magdict, name='mag')
        lumcol = Column(lumdict, name='lum')
        sfrcol = Column(sfrdict, name='sfr')
        newt.add_columns([extcol, magcol, lumcol, sfrcol])

        tablecolnames = ['name', 'ra', 'dec', 'object_type', 'z', 'z_err', 'z_tech', 'z_qual',
                         'z_qual_flag', 'z_refcode', 'z_dist', 'z_dist_err', 'z_dist_method',
                         'z_dist_indicator', 'z_dist_refcode', 'd_l', 'd_l_err', 'dist_method', 
                         'ebv', 'galex_phot', 'tmass_phot', 'wise_phot', 'et_flag', 'm_star', 
                         'm_star_err', 'ml_ratio', 'extinction', 'mag', 'lum', 'sfr']

        # Make dictionaries using the model column names and the rows of the new table
        rows_to_add = [dict(zip(tablecolnames, row)) for row in newt]

        for row in rows_to_add:
            o = NEDLVSCatalog(**row) # Add rows to the db
            o.save()
