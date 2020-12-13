'''
Created on 08-09-2012
@author: Maciej Wasilak

Updated on 28-11-2020
@co-author: Johirul Islam
'''

import sys, time

from ipaddress import ip_address

from twisted.internet import reactor
from twisted.python import log

import txthings.coap as coap
import txthings.resource as resource

from adafruit_dht import read

from config import SLEEP, MODEL, PIN, CoAP_HOST, CoAP_PORT


# ------------------------------ moved to config.py ------------------------------ #
# CoAP settings
# -------------
#CoAP_HOST = os.environ.get("CoAP_HOST", "127.0.0.1")    # CoAP host
#CoAP_HOST=os.environ.get("CoAP_HOST", "localhost")      # CoAP host
#CoAP_PORT = int(os.environ.get("CoAP_PORT", 5683))      # CoAP port

# basic settings
# --------------
#SLEEP     = int(os.environ.get("SLEEP", 5))     # sleep time after a reading 

# DHT config
# ----------
#MODEL = int(os.environ.get("DHT_MODEL", 22))    # model -- 11, 22 or 2302
#PIN   = int(os.environ.get("DHT_PIN", 23))      # pin   -- BCM data pin header
# ------------------------------ moved to config.py ------------------------------ #


class DHTClient:
    """
    Example class which performs single GET request to coap.me
    port 5683 (official IANA assigned CoAP port), URI "test".
    Request is sent 1 second after initialization.
    Remote IP address is hardcoded - no DNS lookup is preformed.
    Method requestResource constructs the request message to
    remote endpoint. Then it sends the message using protocol.request().
    A deferred 'd' is returned from this operation.
    Deferred 'd' is fired internally by protocol, when complete response is received.
    Method printResponse is added as a callback to the deferred 'd'. This
    method's main purpose is to act upon received response (here it's simple print).
    """

    # As DHTClient(protocol, CoAP_HOST, CoAP_PORT, uri, str(humidity)) is commented in main()
    """
    def __init__(self, protocol, host, port, uri, payload):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.uri = uri
        self.payload = payload
        reactor.callLater(1, self.requestResource)
    """

    def __init__(self, protocol, host, port):
        self.protocol = protocol
        self.host = host
        self.port = port
        
        self.next = "temperature"
        self.sleepRequired = False
        
        # send temperature / humidity
        reactor.callLater(0, self.requestResource)
        

    def requestResource(self):
        
        if self.next == "temperature":
            
            # read temperature 
            temperature = read(MODEL, PIN, 'temperature')
            temperature = round(temperature, 1)		
            print "temperature # ", temperature	
            
            # URI for "coap://<host>:<port>/sensors/dht/temperature"
            #uri      = (b'sensors/dht/temperature')
            uri      = (b'sensors', b'dht', b'temperature', )
            self.uri = uri
            self.payload = str(temperature)
            
            self.next = "humidity"
            self.sleepRequired = False
            
        elif self.next == "humidity":
            
            # read humidity 
            humidity = read(MODEL, PIN, 'humidity')
            humidity = round(humidity, 1)	
            print "humidity    # ", humidity
            
            # URI for "coap://<host>:<port>/sensors/dht/temperature"
            uri      = (b'sensors', b'dht', b'humidity', )
    
            # Send request to "coap://<host>:<port>/sensors/dht/<temperature/humidity>"
            #DHTClient(protocol, CoAP_HOST, CoAP_PORT, uri, str(humidity))
            self.uri = uri
            self.payload = str(humidity)  
            
            self.next = "temperature"
            self.sleepRequired = True
        
        print "----------------------- CoAP ------------------------"
        print "host    :", self.host
        print "port    :", self.port
        print "URI     :", self.uri
        print "payload :", self.payload 
        print "----------------------- ends ------------------------"
        
        request = coap.Message(code=coap.POST, payload=self.payload)        
        request.opt.uri_path = self.uri        
        request.opt.observe = 0
        
        # bypass following error --> 
        # ipaddress.AddressValueError: '192.168.1.128' does not appear 
        # to be an IPv4 or IPv6 address. Did you pass in a bytes (str in Python 2) instead of a unicode object?
        #request.remote = (ip_address(self.host), self.port)
        request.remote = (ip_address(unicode(self.host)), self.port)
        
        d = self.protocol.request(request, observeCallback=self.printLaterResponse)
        d.addCallback(self.printResponse)
        d.addErrback(self.noResponse)

    def printResponse(self, response):
        print('First result: ' + str(response.payload))
        # reactor.stop()        
        
        if self.sleepRequired:
            time.sleep(SLEEP)
        
        # send temperature / humidity
        reactor.callLater(0, self.requestResource)
        

    def printLaterResponse(self, response):
        print('Observe result: ' + str(response.payload))
        

    def noResponse(self, failure):
        print('Failed to fetch resource:')
        print(failure)
        # reactor.stop()
    
    """    
    def sendRequest(self):
        # ---------------------------------------------------------------------- #        
        # read temperature 
        temperature = read(MODEL, PIN, 'temperature')
        temperature = round(temperature, 1)		
        print "temperature # ", temperature	
            
        # URI for "coap://<host>:<port>/sensors/dht/temperature"
        #uri      = (b'sensors/dht/temperature')
        uri      = (b'sensors', b'dht', b'temperature', )
    
        # Send request to "coap://<host>:<port>/sensors/dht/temperature"
        #DHTClient(protocol, CoAP_HOST, CoAP_PORT, uri, str(temperature))
        self.uri = uri
        self.payload = str(temperature)
        self.requestResource()
    
            
        # read humidity 
        humidity = read(MODEL, PIN, 'humidity')
        humidity = round(humidity, 1)	
        print "humidity    # ", humidity
            
        # URI for "coap://<host>:<port>/sensors/dht/temperature"
        uri      = (b'sensors', b'dht', b'humidity', )
    
        # Send request to "coap://<host>:<port>/sensors/dht/<temperature/humidity>"
        #DHTClient(protocol, CoAP_HOST, CoAP_PORT, uri, str(humidity))
        self.uri = uri
        self.payload = str(humidity)        
        self.requestResource()
        # /--------------------------------------------------------------------- #
    """



def main():
    log.startLogging(sys.stdout)
    
    
    # Resource tree creation
    # coap://<host>:<port>
    '''root = resource.CoAPResource()'''
    
    # sensors root URL
    # coap://<host>:<port>/sensors
    '''sensors = resource.CoAPResource()
    root.putChild('sensors', sensors)'''
    
    # sensors dynamic URL
    # coap://<host>:<port>/sensors/dht
    '''dht = resource.CoAPResource()
    sensors.putChild('dht', dht)'''


    endpoint = resource.Endpoint(None)
    protocol = coap.Coap(endpoint)
    
    
    """
    # ---------------------------------------------------------------------- #        
    # read temperature 
    temperature = read(MODEL, PIN, 'temperature')
    temperature = round(temperature, 1)		
    print "temperature # ", temperature	
            
    # URI for "coap://<host>:<port>/sensors/dht/temperature"
    #uri      = (b'sensors/dht/temperature')
    uri      = (b'sensors', b'dht', b'temperature', )
    
    # Send request to "coap://<host>:<port>/sensors/dht/temperature"
    DHTClient(protocol, CoAP_HOST, CoAP_PORT, uri, str(temperature))
    
            
    # read humidity 
    humidity = read(MODEL, PIN, 'humidity')
    humidity = round(humidity, 1)	
    print "humidity    # ", humidity
            
    # URI for "coap://<host>:<port>/sensors/dht/temperature"
    uri      = (b'sensors', b'dht', b'humidity', )
    
    # Send request to "coap://<host>:<port>/sensors/dht/<temperature/humidity>"
    DHTClient(protocol, CoAP_HOST, CoAP_PORT, uri, str(humidity))
    # /--------------------------------------------------------------------- #
    """
    
    
    # above functionality made for temperature & humidity reading moved to following
    DHTClient(protocol, CoAP_HOST, CoAP_PORT)
    
            
    reactor.listenUDP(61616, protocol)  # , interface="::")
    reactor.run()
    
        
if __name__ == '__main__':
    
    main()
    
