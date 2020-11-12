import mimetypes
from tom_dataproducts.processors.spectroscopy_processor import SpectroscopyProcessor
from tom_dataproducts.exceptions import InvalidFileFormatException
from tom_dataproducts.processors.data_serializers import SpectrumSerializer

class SpecProcessor(SpectroscopyProcessor):

    FITS_MIMETYPES = ['image/fits', 'application/fits']
    PLAINTEXT_MIMETYPES = ['text/plain', 'text/csv']
    
    def process_data(self, data_product, extras):
    
        mimetype = mimetypes.guess_type(data_product.data.path)[0]
        if mimetype in self.FITS_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_fits(data_product)
        elif mimetype in self.PLAINTEXT_MIMETYPES:
            spectrum, obs_date = self._process_spectrum_from_plaintext(data_product)
        else:
            raise InvalidFileFormatException('Unsupported file type')

        serialized_spectrum = SpectrumSerializer().serialize(spectrum)

        return [(obs_date, serialized_spectrum)]
