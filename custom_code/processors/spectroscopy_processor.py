import mimetypes
from tom_dataproducts.processors.spectroscopy_processor import SpectroscopyProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException
from tom_dataproducts.processors.data_serializers import SpectrumSerializer
from tom_observations.facility import get_service_class, get_service_classes
from django.core.files.storage import default_storage
from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
from astropy import units
from specutils import Spectrum1D
from datetime import datetime

class SpecProcessor(SpectroscopyProcessor):

    FITS_MIMETYPES = ['image/fits', 'application/fits']
    PLAINTEXT_MIMETYPES = ['text/plain', 'text/csv']
    DEFAULT_FLUX_CONSTANT = (1e-15 * units.erg) / units.cm ** 2 / units.second / units.angstrom
 
    def process_data(self, data_product, extras):
        print('Using the custom Spec Processor to process data') 
        mimetype = mimetypes.guess_type(data_product.data.name)[0]
        if mimetype in self.FITS_MIMETYPES:
            print('Identified file as fits and processing spectrum')
            spectrum, obs_date = self._process_spectrum_from_fits(data_product)
        elif mimetype in self.PLAINTEXT_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_plaintext(data_product)
        else:
            raise InvalidFileFormatException('Unsupported file type')
        print('Serializing spectrum...')
        serialized_spectrum = SpectrumSerializer().serialize(spectrum)

        return [(obs_date, serialized_spectrum)]

    def _process_spectrum_from_fits(self, data_product):

        data_aws = default_storage.open(data_product.data.name, 'rb')
        print(data_aws)
        print(type(data_aws))
                

        flux, header = fits.getdata(data_aws.open(), header=True)
        print('Got fits data')
        
        for facility_class in get_service_classes():
            facility = get_service_class(facility_class)()
            import pdb
            pdb.set_trace()
            if facility.is_fits_facility(header):
                flux_constant = facility.get_flux_constant()
                date_obs = facility.get_date_obs(header)
                break
        else:
            flux_constant = self.DEFAULT_FLUX_CONSTANT
            date_obs = datetime.now()
        print('Got flux constant')
        dim = len(flux.shape)
        if dim == 3:
            flux = flux[0, 0, :]
        elif flux.shape[0] == 2:
            flux = flux[0, :]
        flux = flux * flux_constant

        header['CUNIT1'] = 'Angstrom'
        wcs = WCS(header=header, naxis=1)

        spectrum = Spectrum1D(flux=flux, wcs=wcs)

        return spectrum, Time(date_obs).to_datetime()
