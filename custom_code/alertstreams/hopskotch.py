from datetime import datetime, timezone
import logging
from hop.models import JSONBlob
from hop.io import Metadata
from tom_alertstreams.alertstreams.alertstream import AlertStream
from django.core.exceptions import ImproperlyConfigured
from django.utils import timezone as tz

from hop import Stream
from hop.auth import Auth
from hop.models import JSONBlob
from hop.io import Metadata, StartPosition, list_topics
import re
import uuid

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class CustomHopskotchAlertStream(AlertStream):

    required_keys = ['URL', 'GROUP_ID', 'USERNAME', 'PASSWORD', 'TOPIC_HANDLERS']
    allowed_keys = ['URL', 'GROUP_ID', 'USERNAME', 'PASSWORD', 'TOPIC_HANDLERS']
    PUBLIC_TOPIC_CHECK_INTERVAL = 300  # Seconds between checking for new public topics
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        # the following methods may fail if improperly configured.
        # So, do them now to catch any errors, before listen() is spawned in it's own Process.
        self.public_topics = self.get_all_public_topics()
        self.stream_url = self.get_stream_url()
        self.stream = self.get_stream()

    def get_all_public_topics(self) -> list:
        """Returns the up-to-date list of Topic names to consume.
        Use the saved options to repeatedly construct the topic list, and
        keep it in sync with the publicaly_readable topics from SCiMMA Auth.
        The Topic list is a combination of the
          a. the publicly_readable Topics from SCiMMA Auth
          b. any topics supplied on the command line via -T, --topic
        """
        hop_auth = Auth(self.username, self.password)
        logger.info('getting publicly_readable topics from SCiMMA Auth.')
        # use the hop-client to ask Kafka directly for the topics since SCiMMA Auth can be out of sync
        # include only topics that a) contain a '.'; b) don't start with '__' (excludes __consumer_offsets)
        publicly_readable_topics = [topic for topic in list_topics(self.url, hop_auth).keys()
                                    if not (topic.startswith('__') and (topic.count('.')==0))]
        logger.info(f'publicly_readable_topics: {publicly_readable_topics}')

        return publicly_readable_topics

    def get_stream_url(self) -> str:
        """For Hopskotch, topics are specified on the url. So, this
        method gets a base url (from super) and then adds topics to it.
        Hopskotch (hop.io) requires at least one topic to be specified.
        You might not need a method like this if your Kafka client provides
        alternative ways to subscribe to a topic. For example, the gcn_kafka.Consumer
        class provides a 'substribe([list of topics])' method. (see gcn.py).
        """
        logger.debug(f'HopskotchAlertStream.get_stream_url topics: {list(self.topic_handlers.keys())}')
        if self.topic_handlers == {}:
            msg = 'Hopskotch requires at least one topic to open the stream. Check ALERT_STREAMS in settings.py'
            raise ImproperlyConfigured(msg)

        base_stream_url = self.url

        # if not present, add trailing slash to base_stream url
        # so, comma-separated topics can be appeneded.
        if base_stream_url[-1] != '/':
            base_stream_url += '/'

        # append comma-separated topics to base URL
        specified_topics = list(self.topic_handlers.keys())
        if '*' in specified_topics:
            # Add all public topics if a asterisk is set in the topic_handlers
            specified_topics = list(set(specified_topics + self.public_topics))
        # Also remove topics with wildcards in them
        specified_topics = [topic for topic in specified_topics if not '*' in topic]

        topics = ','.join(specified_topics)  # 'topic1,topic2,topic3'
        hopskotch_stream_url = base_stream_url + topics

        logger.debug(f'HopskotchAlertStream.get_stream_url url: {hopskotch_stream_url}')
        return hopskotch_stream_url

    def get_stream(self, start_position=StartPosition.LATEST) -> Stream:
        hop_auth = Auth(self.username, self.password)

        # TODO: allow StartPosition to be set from OPTIONS configuration dictionary
        stream = Stream(auth=hop_auth, start_at=start_position)
        return stream

    def listen(self):
        super().listen()
        # TODO: alternatively, WARN upon OPTIONS['topics'] extries that don't have
        # handlers in the alert_handler. (i.e they've configured a topic subscription
        # without providing a handler for the topic. So, warn them).
        last_check_time = tz.now()
        while True:
            try:
                logger.info(f'HopskotchAlertStream.listen opening stream: {self.stream_url} with group_id: {self.group_id}')
                with self.stream.open(self.stream_url, 'r', group_id=self.group_id) as src:
                    for alert, metadata in src.read(metadata=True):
                        # type(gcn_circular) is <hop.models.GNCCircular>
                        # type(metadata) is <hop.io.Metadata>
                        if metadata.topic in self.alert_handler:
                            # TODO: should probably use *args, **kwargs to pass unknow number of arguments
                            self.alert_handler[metadata.topic](alert, metadata)
                        elif '*' in self.alert_handler:
                            # First check all wildcard topics to see if they will match this topic
                            matched_handler = False
                            for topic in self.alert_handler.keys():
                                if '*' in topic and re.match(topic, metadata.topic):
                                    self.alert_handler[topic](alert, metadata)
                                    matched_handler = True
                                    break
                            # If nothing matched, fall back to default public topic handler
                            if not matched_handler:
                                self.alert_handler['*'](alert, metadata)
                        else:
                            logger.error(f'alert from topic {metadata.topic} received but no handler defined.')
                            # TODO: should define a default handler for all unhandeled topics
                        if (tz.now() - last_check_time).total_seconds() > self.PUBLIC_TOPIC_CHECK_INTERVAL:
                            last_check_time = tz.now()
                            public_topics = self.get_all_public_topics()
                            if set(public_topics) != set(self.public_topics):
                                logger.info(f"New public topics found, restarting hop stream")
                                self.public_topics = public_topics
                                self.stream_url = self.get_stream_url()
                                break
            except Exception as ex:
                logger.error(f'HopskotchAlertStream.listen: {ex}')


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


def alert_logger(alert: JSONBlob, metadata: Metadata):
    """Example alert handler. The method signsture is specific to Hopskotch alerts.
    """
    # search the header (list of tuples) for a UUID-tuple (keyed by '_id')
    # eg. ('_id', b'$\xd6oGmVM\xed\x97\xe7|\x1c\x8f\x11V\xe9')
    alert_uuid_tuple = next((item for item in metadata.headers if item[0] == '_id'), None)
    if alert_uuid_tuple:
        alert_uuid = uuid.UUID(bytes=alert_uuid_tuple[1])
    else:
        # in this case the alert was probably published with hop-client<0.8.0
        alert_uuid = None
    logger.info(f'Alert (uuid={alert_uuid}) received on topic {metadata.topic}: {alert};  metatdata: {metadata}')


def heartbeat_handler(heartbeat: JSONBlob, metadata: Metadata):
    """Example alert handler for HopskotchAlertStream sys.heartbeat topic.
    Note that HopskotchAlertStream.listen() method knows that Hopskotch alerts come with
    both alert and metadata. So, the alert_handler methods have a signiture (taking both
    as arguments) specific to this stream.
    """
    content: dict = heartbeat.content  # see hop_client reatthedocs
    timestamp = datetime.fromtimestamp(content["timestamp"] / 1e6, tz=timezone.utc)
    if heartbeat.content['count'] % 10 == 0:
        # mod 300 just for convenience so as not to flood logger
        logging.info(f'{timestamp.isoformat()} heartbeat.content dict: {heartbeat.content}. metadata: {metadata}')
