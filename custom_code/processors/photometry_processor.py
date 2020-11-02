import mimetypes
import json

from astropy import units
from astropy.io import ascii
from astropy.time import Time, TimezoneInfo
from django.core.files.storage import default_storage

from tom_dataproducts.data_processor import DataProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException


class PhotometryProcessor(DataProcessor):

    def process_data(self, data_product, extras):

        mimetype = mimetypes.guess_type(data_product.data.name)[0]
        if mimetype in self.PLAINTEXT_MIMETYPES:
            photometry = self._process_photometry_from_plaintext(data_product, extras)
            return [(datum.pop('timestamp'), json.dumps(datum)) for datum in photometry]
        else:
            raise InvalidFileFormatException('Unsupported file type')

    def _process_photometry_from_plaintext(self, data_product, extras):

        photometry = []

        data_aws = default_storage.open(data_product.data.name, 'r')
        data = ascii.read(data_aws.read(),
                          names=['time', 'filter', 'magnitude', 'error'])

        if len(data) < 1:
            raise InvalidFileFormatException('Empty table or invalid file type')

        for datum in data:
            time = Time(float(datum['time']), format='mjd')
            utc = TimezoneInfo(utc_offset=0*units.hour)
            time.format = 'datetime'
            value = {
                'timestamp': time.to_datetime(timezone=utc),
                'magnitude': datum['magnitude'],
                'filter': datum['filter'],
                'error': datum['error']
            }
            value.update(extras)

            photometry.append(value)

        return photometry


class PipelineProcessor(DataProcessor):

    def process_data(self, data_product, extras):

        mimetype = mimetypes.guess_type(data_product.data.name)[0]
        if mimetype in self.PLAINTEXT_MIMETYPES:
            photometry = self._process_photometry_from_plaintext(data_product, extras)
            return [(datum.pop('timestamp'), json.dumps(datum)) for datum in photometry]
        else:
            raise InvalidFileFormatException('Unsupported file type')

    def _process_photometry_from_plaintext(self, data_product, extras):

        photometry = []
        data_aws = default_storage.open(data_product.data.name, 'r')
        #data = ascii.read(data_product.data.path)
        data = ascii.read(data_aws.read(),
                          names=['time', 'filter', 'magnitude', 'error'])
        if len(data) < 1:
            raise InvalidFileFormatException('Empty table or invalid file type')

        for datum in data:
            time = Time(float(datum['time']), format='mjd')
            utc = TimezoneInfo(utc_offset=0*units.hour)
            time.format = 'datetime'
            value = {
                'timestamp': time.to_datetime(timezone=utc),
                'magnitude': datum['magnitude'],
                'filter': datum['filter'],
                'error': datum['error']
            }
            value.update(extras)

            photometry.append(value)

        return photometry

