from custom_code.models import GladeCatalog
from django.core.management.base import BaseCommand


class Command(BaseCommand):

    help = 'Ingests the GLADE+ catalog into the database'

    def add_arguments(self, parser):
        parser.add_argument('--filename', help='Ingest catalog information from this file')


    def handle(self, *args, **options):

        filename = options['filename']

        with open(filename, 'r') as f:

            lines = f.readlines()
            column_names = ['pgc_no', 'gwgc_name', 'hyperleda_name', 'twomass_name', 
                            'wisexscos_name', 'sdss_dr16q_name', 'object_type_flag',
                            'ra', 'dec']

            column_types = ['int', 'str', 'str', 'str', 'str', 'str', 'str', 'float', 'float']

            mag_dict_keys = ['B', 'B_err', 'B_flag', 'B_abs', 'J', 'J_err', 'H', 'H_err',
                             'K', 'K_err', 'W1', 'W1_err', 'W2', 'W2_err', 'W1_flag', 'B_J',
                             'B_J_err']

            column_names_two = ['z_helio', 'z_cmb', 'z_flag', 'v_err', 'z_err', 'd_l', 'd_l_err',
                                'dist_flag', 'm_star', 'm_star_err', 'm_star_flag', 'merger_rate',
                                'merger_rate_err']

            column_types_two = ['float', 'float', 'int', 'float', 'float', 'float', 'float', 'int',
                                'float', 'float', 'int', 'float', 'float']
            
            for line in lines:
                ### Insert into database
                x = line.split()
                param_dict = {}

                for i in range(len(column_names)):
                    if x[i+1] != 'null':

                        if column_types[i] == 'int':
                            param_dict[column_names[i]] = int(x[i+1])

                        elif column_types[i] == 'float':
                            param_dict[column_names[i]] = float(x[i+1])

                        else:
                            param_dict[column_names[i]] = x[i+1]

                mag_dict = {}

                for i in range(len(mag_dict_keys)):
                    if x[i+len(column_names)+1] != 'null' and 'flag' not in mag_dict_keys[i]:
                        
                        mag_dict[mag_dict_keys[i]] = float(x[i+len(column_names)+1])
                    
                    elif x[i+len(column_names)+1] != 'null':

                        mag_dict[mag_dict_keys[i]] = int(x[i+len(column_names)+1])

                param_dict['mag'] = mag_dict

                for i in range(len(column_names_two)):
                    if x[i+len(column_names)+len(mag_dict_keys)+1] != 'null':

                        if column_types_two[i] == 'int':
                            param_dict[column_names_two[i]] = int(x[i+len(column_names)+len(mag_dict_keys)+1])

                        elif column_types_two[i] == 'float':
                            param_dict[column_names_two[i]] = float(x[i+len(column_names)+len(mag_dict_keys)+1])

                        else:
                            param_dict[column_names_two[i]] = x[i+len(column_names)+len(mag_dict_keys)+1]

                g = GladeCatalog(**param_dict)
                g.save()
