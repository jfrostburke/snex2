from tom_alerts.brokers.mars import MARSBroker


class CustomMARSBroker(MARSBroker):

    def process_reduced_data(self, target, alert=None):
        pass
    
