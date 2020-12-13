import datetime

import txthings.coap as coap
import txthings.resource as resource

from twisted.python import log
from twisted.internet import defer
from twisted.internet import reactor

from database import send_influxdb


__author__ = 'Johirul Islam'


class TimeResource(resource.CoAPResource):
    def __init__(self):
        resource.CoAPResource.__init__(self)
        self.visible = True
        self.observable = True

        self.notify()

    def notify(self):
        log.msg('TimeResource: trying to send notifications')
        self.updatedState()
        reactor.callLater(60, self.notify)

    def render_GET(self, request):
        response = coap.Message(code=coap.CONTENT, payload=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
        return defer.succeed(response)


class CoreResource(resource.CoAPResource):
    """
    Example Resource that provides list of links hosted by a server.
    Normally it should be hosted at /.well-known/core
    Resource should be initialized with "root" resource, which can be used
    to generate the list of links.
    For the response, an option "Content-Format" is set to value 40,
    meaning "application/link-format". Without it most clients won't
    be able to automatically interpret the link format.
    Notice that self.visible is not set - that means that resource won't
    be listed in the link format it hosts.
    """

    def __init__(self, root):
        resource.CoAPResource.__init__(self)
        self.root = root

    def render_GET(self, request):
        data = []
        self.root.generateResourceList(data, "")
        payload = ",".join(data)
        log.msg("%s", payload)
        response = coap.Message(code=coap.CONTENT, payload=payload)
        response.opt.content_format = coap.media_types_rev['application/link-format']
        return defer.succeed(response)


# ---------------------------------------------------------------------- #
class DHTResource(resource.CoAPResource):
    """
    DHTResource is responsible for storing temperature & 
    humidity data sent by a client connected with DHT22.
    """

    def __init__(self, path):
        resource.CoAPResource.__init__(self)
        self.visible = True
        # dynamic URL part from --> coap://<host>:<port>/sensors/dht/<temperature/humidity>
        # passed by DynamicURLResource
        self.dynamicURL = path
        title = "DHT resource is responsible for adding new temperature/humidity data into the database"
        self.addParam(resource.LinkParam("title", title))

    def render_POST(self, request):
        # dynamic URL part from --> coap://<host>:<port>/sensors/dht/<temperature/humidity>
        dynamicURL = self.dynamicURL            
        print "New request found for ... ... ... ", dynamicURL
        
        # payload/data that coming from CoAP client having DHT sensor
        print "payload found ... ... ...: ", request.payload
        data = float(request.payload)
        print "New request found for ... ... ... ", dynamicURL
        
        '''if self.dynamicURL == 'temperature':
            send_influxdb(data, 'temperature')
        elif request.uri_path == 'humidity':
            send_influxdb(data, 'humidity')'''
        
        # capitalize temparature/humidity i.e the 
        # dynamicURL part with dynamicURL.title()
        payload = "Unable to save %s data!" % dynamicURL.title()
        
        if dynamicURL == 'temperature' or dynamicURL == 'humidity':
            send_influxdb(data, dynamicURL)
            print "Saving ", data, " to ", dynamicURL
            payload = "%s saved successfully!" % dynamicURL.title()
        else:
            print "Unknown Resource with ", data
        
        defer_obj = defer.Deferred()
        reactor.callLater(0, self.responseReady, defer_obj, request, payload)
        return defer_obj
        
    def responseReady(self, d, request, payload):
        log.msg('response ready. sending...')
        response = coap.Message(code=coap.CONTENT, payload=payload)
        d.callback(response)

class DynamicURLResource(resource.CoAPResource):
    """
    DynamicURLResource is responsible for getting sub URL i.e temperature/humidity 
    part (last one) from coap://<host>:<port>/sensors/dht/<temperature/humidity>.
    """
        
    def getChild(self, path, request):
        # print "----------------", request.prepath
        # print "----------------", path
        return DHTResource(path)
# /--------------------------------------------------------------------- #
