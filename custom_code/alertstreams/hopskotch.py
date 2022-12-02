from datetime import datetime, timezone
import logging
from hop.models import JSONBlob
from hop.io import Metadata


logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def alert_handler(alert: JSONBlob, metadata: Metadata):
    
    logger.info(f'Alert received on topic {metadata.topic}: {alert};  metatdata: {metadata}')

    ### Retrieve target information and check if target exists; if not, add it

    ### Check if this message has already been ingested; if not, add it

    ### Parse data in SNEx2-readable format, and save
    if alert.content['data'].get('photometry_data', ''):
        rds = []
        for datum in alert.content['data']['photometry_data']:
            rd = ReducedDatum(target_id=target_id, data_type='photometry', 
                    timestamp=datetime.utcnow(), 
                    value={'magnitude': datum['brightness'], 'filter': datum['band'],
                           'error': datum['brightnessError']
                    },
                    message=message #TODO: Add above
            )
            rd.save()                                
            rds.append(rd)

    ### Save any ReducedDatumExtra rows, if needed

    #logger.info('Data saved successfully')

