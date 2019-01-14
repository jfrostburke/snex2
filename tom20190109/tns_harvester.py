from tom_catalogs.harvester import AbstractHarvester

import requests
import json
import os

class TNSClient(object):
    """Send Bulk TNS Request."""

    def __init__(self, baseURL, options = {}):
        """
        Constructor. 

        :param baseURL: Base URL of the TNS API
        :param options:  (Default value = {})

        """
        
        #self.baseAPIUrl = TNS_BASE_URL_SANDBOX
        self.baseAPIUrl = baseURL
        self.generalOptions = options

    def buildUrl(self, resource):
        """
        Build the full URL

        :param resource: the resource requested
        :return complete URL

        """
        return self.baseAPIUrl + resource

    def buildParameters(self, parameters = {}):
        """
        Merge the input parameters with the default parameters created when
        the class is constructed.

        :param parameters: input dict  (Default value = {})
        :return p: merged dict

        """
        p = self.generalOptions.copy()
        p.update(parameters)
        return p

    def jsonResponse(self, r):
        """
        Send JSON response given requests object. Should be a python dict.

        :param r: requests object - the response we got back from the server
        :return d: json response converted to python dict

        """

        d = {}
        # What response did we get?
        message = None
        status = r.status_code

        if message is not None:
            return d
        
        # Did we get a JSON object?
        d = r.json()

        # If so, what error messages if any did we get?

        if 'id_code' in d.keys() and 'id_message' in d.keys() and d['id_code'] != 200:
            logger.error("Bad response: code = %d, error = '%s'" % (d['id_code'], d['id_message']))
        return d


    def sendBulkReport(self, options, resource):
        """
        Send the JSON TNS request

        :param options: the JSON TNS request
        :return: dict

        """
        feed_url = self.buildUrl(resource);
        feed_parameters = self.buildParameters({'data': json.dumps(options)});
        
        r = requests.post(feed_url, data = feed_parameters, timeout = 300)
        # Construct the JSON response and return it.
        return self.jsonResponse(r)

    def bulkReportReply(self, options):
        """
        Get the report back from the TNS

        :param options: dict containing the report ID
        :return: dict

        """
        feed_url = self.buildUrl(AT_REPORT_REPLY);
        feed_parameters = self.buildParameters(options);

        r = requests.post(feed_url, files = feed_parameters, timeout = 300)
        return self.jsonResponse(r)

def get_tns_info(name):
        
    resource = "object"
        
    sandbox = False

    if sandbox:
        TNS_BASE_URL = "https://sandbox-tns.weizmann.ac.il/api/get/"
    else:
        TNS_BASE_URL = "https://wis-tns.weizmann.ac.il/api/get/"
    API_KEY = os.environ['SNEXBOT_APIKEY']
    
    prop_request = {"objname": "%s" %name,
                    "photometry": "1",
                    "spectra": "1",
                    }
    feed_handler = TNSClient(TNS_BASE_URL, {'api_key': (None, API_KEY)})
    response = feed_handler.sendBulkReport(prop_request,resource)
    if response:
        return(response['data']['reply'])
    else:
        return(0,'',[])

def convert_radec(ra,dec):
    
    [hr,mi,se] = [float(x) for x in ra.split(':')]
    
    ra_hr = hr + mi/60. + se/3600.
    ra_deg = (ra_hr/24.)*360.
    
    [de,mi,se] = [abs(float(x)) for x in dec.split(':')]
    
    dec_deg = de + mi/60. + se/3600.
    if '-' in dec: dec_deg = -dec_deg
    
    return ra_deg, dec_deg


class TNSHarvester(AbstractHarvester):
    name = 'TNS'

    def query(self, term):
        self.catalog_data = get_tns_info(term)

    def to_target(self):
        target = super().to_target()
        target.type = 'SIDEREAL'
        target.identifier = self.catalog_data['name_prefix']+self.catalog_data['name']
        target.ra, target.dec = convert_radec(
            self.catalog_data['ra'], self.catalog_data['dec'])
        return target
