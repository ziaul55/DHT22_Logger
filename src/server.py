'''
Created on 08-09-2012
@author: Maciej Wasilak

Updated on 28-11-2020
@co-authors: Johirul Islam; Md. Ziaul Hoque
'''

import sys

from twisted.python import log
from twisted.internet import defer
from twisted.internet import reactor

import txthings.coap as coap
import txthings.resource as resource

from resources import CoreResource, TimeResource, DHTResource, DynamicURLResource

def main():
    
    # start log to the console
    log.startLogging(sys.stdout)

    # Resource tree creation
    # coap://<host>:<port>
    root = resource.CoAPResource()

    # coap://<host>:<port>/.well-known
    well_known = resource.CoAPResource()
    root.putChild('.well-known', well_known)

    # coap://<host>:<port>/core
    core = CoreResource(root)
    well_known.putChild('core', core)
    
    # coap://<host>:<port>/time
    time = TimeResource()
    root.putChild('time', time)
    
    # ---------------------------------------------------------------------- #
    # sensors root URL
    # coap://<host>:<port>/sensors
    sensors = resource.CoAPResource()
    root.putChild('sensors', sensors)

    # sensors child URL
    # coap://<host>:<port>/sensors/register
    #register = RegistryResource()
    #sensors.putChild('register', register)
    
    # sensors dynamic URL
    # coap://<host>:<port>/sensors/dht/<temperature/humidity>
    dynamic_url = DynamicURLResource()
    sensors.putChild('dht', dynamic_url)
    # /--------------------------------------------------------------------- #

    endpoint = resource.Endpoint(root)

    reactor.listenUDP(coap.COAP_PORT, coap.Coap(endpoint))  # , interface="::")
    reactor.run()



if __name__ == '__main__':
    main()
