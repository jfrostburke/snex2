from importlib import import_module
from django.conf import settings
from tom_dataproducts.models import ReducedDatum

DEFAULT_DATA_PROCESSOR_CLASS = 'tom_dataproducts.data_processor.DataProcessor'

def run_custom_data_processor(dp, extras):
    try:
        processor_class = settings.DATA_PROCESSORS[dp.data_product_type]
    except Exception:
        processor_class = DEFAULT_DATA_PROCESSOR_CLASS

    try:
        mod_name, class_name = processor_class.rsplit('.', 1)
        mod = import_module(mod_name)
        clazz = getattr(mod, class_name)
    except (ImportError, AttributeError):
        raise ImportError('Could not import {}. Did you provide the correct path?'.format(processor_class))

    data_processor = clazz()
    data = data_processor.process_data(dp, extras)

    reduced_datums = [ReducedDatum(target=dp.target, data_product=dp, data_type=dp.data_product_type,
                                   timestamp=datum[0], value=datum[1]) for datum in data]
    ReducedDatum.objects.bulk_create(reduced_datums)

    return ReducedDatum.objects.filter(data_product=dp)


