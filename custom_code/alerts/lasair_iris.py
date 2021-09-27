from tom_alerts.alerts import GenericQueryForm, GenericAlert, GenericBroker
import requests
import os

LASAIR_IRIS_URL = 'https://lasair-iris.roe.ac.uk'


@dataclass
class LasairIrisGenericAlert(GenericAlert):

    id: int
    name: str
    ra: float
    dec: float
    url: str
    phot: dict
    

class LasairIrisBrokerForm(GenericQueryForm):
    name = forms.CharField(required=True, label='Stream Name', help_text='Name of Lasair Stream')
    limit = forms.IntegerField(required=True, label='Number of Targets', help_text='Number of Targets to Ingest')

class LasairIrisBroker(GenericBroker):
    
    name = 'Lasair Iris'
    form = LasairIrisBrokerForm

    def __init__(self, *args, **kwargs):
        self.token = os.environ['LASAIR_APIKEY'] 
        #self.headers = {'Authorization': 'Token ' + os.environ['LASAIR_APIKEY']}

    def fetch_alerts(self, parameters):
        """
        Fetch results from a Lasair stream
        """
        stream_name = parameters['name']
        limit = parameters['limit']
        token = self.token

        response = requests.get(f'{LASAIR_IRIS_URL}/api/streams/{stream_name}/?limit={limit}&token={token}')
        r = response.json()

        return iter([obj for obj in r])

