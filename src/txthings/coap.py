'''
Created on 08-09-2012

@author: Maciej Wasilak
'''
from itertools import chain
import codecs
import collections
import copy
import random
import struct
import sys

from twisted.internet import protocol, defer, reactor
from twisted.python import log, failure
import txthings.error as error

from ipaddress import ip_address

import six

COAP_PORT = 5683
"""The IANA-assigned standard port for COAP services."""

#   +-------------------+---------------+
#   | name              | default value |
#   +-------------------+---------------+
#   | ACK_TIMEOUT       | 2 seconds     |
#   | ACK_RANDOM_FACTOR | 1.5           |
#   | MAX_RETRANSMIT    | 4             |
#   | NSTART            | 1             |
#   | DEFAULT_LEISURE   | 5 seconds     |
#   | PROBING_RATE      | 1 Byte/second |
#   +-------------------+---------------+

ACK_TIMEOUT = 2.0
"""The time, in seconds, to wait for an acknowledgement of a
confirmable message. The inter-transmission time doubles
for each retransmission."""

ACK_RANDOM_FACTOR = 1.5
"""Timeout multiplier for anti-synchronization."""

MAX_RETRANSMIT = 4
"""The number of retransmissions of confirmable messages to
non-multicast endpoints before the infrastructure assumes no
acknowledgement will be received."""

NSTART = 1
"""Maximum number of simultaneous outstanding interactions
   that endpoint maintains to a given server (including proxies)"""

#   +-------------------+---------------+
#   | name              | default value |
#   +-------------------+---------------+
#   | MAX_TRANSMIT_SPAN |          45 s |
#   | MAX_TRANSMIT_WAIT |          93 s |
#   | MAX_LATENCY       |         100 s |
#   | PROCESSING_DELAY  |           2 s |
#   | MAX_RTT           |         202 s |
#   | EXCHANGE_LIFETIME |         247 s |
#   | NON_LIFETIME      |         145 s |
#   +-------------------+---------------+

MAX_TRANSMIT_SPAN = ACK_TIMEOUT * (2 ** MAX_RETRANSMIT - 1) * ACK_RANDOM_FACTOR
"""Maximum time from the first transmission
of a confirmable message to its last retransmission."""

MAX_TRANSMIT_WAIT = ACK_TIMEOUT * (2 ** (MAX_RETRANSMIT + 1) - 1) * ACK_RANDOM_FACTOR
"""Maximum time from the first transmission
of a confirmable message to the time when the sender gives up on
receiving an acknowledgement or reset."""

MAX_LATENCY = 100.0
"""Maximum time a datagram is expected to take from the start
of its transmission to the completion of its reception."""

PROCESSING_DELAY = ACK_TIMEOUT
""""Time a node takes to turn around a
confirmable message into an acknowledgement."""

MAX_RTT = 2 * MAX_LATENCY + PROCESSING_DELAY
"""Maximum round-trip time."""

EXCHANGE_LIFETIME = MAX_TRANSMIT_SPAN + MAX_RTT
"""time from starting to send a confirmable
 message to the time when an acknowledgement is no longer expected,
i.e. message layer information about the message exchange can be purged"""

DEFAULT_BLOCK_SIZE_EXP = 2  # Block size 64
"""Default size exponent for blockwise transfers."""

EMPTY_ACK_DELAY = 0.1
"""After this time protocol sends empty ACK, and separate response"""

REQUEST_TIMEOUT = MAX_TRANSMIT_WAIT
"""Time after which server assumes it won't receive any answer.
   It is not defined by IETF documents.
   For human-operated devices it might be preferable to set some small value
   (for example 10 seconds)
   For M2M it's application dependent."""

CON = 0
"""Confirmable message type."""

NON = 1
"""Non-confirmable message type."""

ACK = 2
"""Acknowledgement message type."""

RST = 3
"""Reset message type"""

types = {0: 'CON',
         1: 'NON',
         2: 'ACK',
         3: 'RST'}


EMPTY = 0
GET = 1
POST = 2
PUT = 3
DELETE = 4
CREATED = 65
DELETED = 66
VALID = 67
CHANGED = 68
CONTENT = 69
CONTINUE = 95
BAD_REQUEST = 128
UNAUTHORIZED = 129
BAD_OPTION = 130
FORBIDDEN = 131
NOT_FOUND = 132
METHOD_NOT_ALLOWED = 133
NOT_ACCEPTABLE = 134
REQUEST_ENTITY_INCOMPLETE = 136
PRECONDITION_FAILED = 140
REQUEST_ENTITY_TOO_LARGE = 141
UNSUPPORTED_CONTENT_FORMAT = 143
INTERNAL_SERVER_ERROR = 160
NOT_IMPLEMENTED = 161
BAD_GATEWAY = 162
SERVICE_UNAVAILABLE = 163
GATEWAY_TIMEOUT = 164
PROXYING_NOT_SUPPORTED = 165

requests = {1: 'GET',
            2: 'POST',
            3: 'PUT',
            4: 'DELETE'}

requests_rev = {v:k for k, v in requests.items()}

responses = {65: '2.01 Created',
             66: '2.02 Deleted',
             67: '2.03 Valid',
             68: '2.04 Changed',
             69: '2.05 Content',
             95: '2.31 Continue',
             128: '4.00 Bad Request',
             129: '4.01 Unauthorized',
             130: '4.02 Bad Option',
             131: '4.03 Forbidden',
             132: '4.04 Not Found',
             133: '4.05 Method Not Allowed',
             134: '4.06 Not Acceptable',
             136: '4.08 Request Entity Incomplete',
             140: '4.12 Precondition Failed',
             141: '4.13 Request Entity Too Large',
             143: '4.15 Unsupported Content-Format',
             160: '5.00 Internal Server Error',
             161: '5.01 Not Implemented',
             162: '5.02 Bad Gateway',
             163: '5.03 Service Unavailable',
             164: '5.04 Gateway Timeout',
             165: '5.05 Proxying Not Supported'}

responses_rev = {v:k for k, v in responses.items()}

#=============================================================================
# RFC7252, block-14, observe-11
#=============================================================================
# +-----+---+---+---+---+----------------+------------+--------+-------------+
# | No. | C | U | N | R | Name           | Format     | Length | Default     |
# +-----+---+---+---+---+----------------+------------+--------+-------------+
# |   1 | x |   |   | x | If-Match       | opaque     | 0-8    | (none)      |
# |   3 | x | x | - |   | Uri-Host       | string     | 1-255  | (see below) |
# |   4 |   |   |   | x | ETag           | opaque     | 1-8    | (none)      |
# |   5 | x |   |   |   | If-None-Match  | empty      | 0      | (none)      |
# |   6 |   | x |   |   | Observe        | empty/uint | ?      | (none)      |
# |   7 | x | x | - |   | Uri-Port       | uint       | 0-2    | (see below) |
# |   8 |   |   |   | x | Location-Path  | string     | 0-255  | (none)      |
# |  11 | x | x | - | x | Uri-Path       | string     | 0-255  | (none)      |
# |  12 |   |   |   |   | Content-Format | uint       | 0-2    | (none)      |
# |  14 |   | x |   |   | Max-Age        | uint       | 0-4    | 60          |
# |  15 | x | x | - | x | Uri-Query      | string     | 0-255  | (none)      |
# |  17 | x |   |   |   | Accept         | uint       | 0-2    | (none)      |
# |  20 |   |   |   | x | Location-Query | string     | 0-255  | (none)      |
# |  23 | x | x | - | - | Block2         | uint       | 0-3    | (see below) |
# |  27 | x | x | - | - | Block1         | uint       | 0-3    | (see below) |
# |  28 |   |   | x |   | Size2          | uint       | 0-4    | (none)      |
# |  35 | x | x | - |   | Proxy-Uri      | string     | 1-1034 | (none)      |
# |  39 | x | x | - |   | Proxy-Scheme   | string     | 1-255  | (none)      |
# |  60 |   |   | x |   | Size1          | uint       | 0-4    | (none)      |
# +-----+---+---+---+---+----------------+------------+--------+-------------+
#=============================================================================
#
# This table should serve as a reference only. It does not confirm that
# txThings conforms to the documents above
#

IF_MATCH = 1
URI_HOST = 3
ETAG = 4
IF_NONE_MATCH = 5
OBSERVE = 6
URI_PORT = 7
LOCATION_PATH = 8
URI_PATH = 11
CONTENT_FORMAT = 12
MAX_AGE = 14
URI_QUERY = 15
ACCEPT = 17
LOCATION_QUERY = 20
BLOCK2 = 23
BLOCK1 = 27
SIZE2 = 28
PROXY_URI = 35
PROXY_SCHEME = 39
SIZE1 = 60

options = {1: 'If-Match',
           3: 'Uri-Host',
           4: 'ETag',
           5: 'If-None-Match',
           6: 'Observe',
           7: 'Uri-Port',
           8: 'Location-Path',
           11: 'Uri-Path',
           12: 'Content-Format',
           14: 'Max-Age',
           15: 'Uri-Query',
           17: 'Accept',
           20: 'Location-Query',
           23: 'Block2',
           27: 'Block1',
           28: 'Size2',
           35: 'Proxy-Uri',
           39: 'Proxy-Scheme',
           60: 'Size1'}

options_rev = {v:k for k, v in options.items()}

media_types = {0: 'text/plain',
               40: 'application/link-format',
               41: 'application/xml',
               42: 'application/octet-stream',
               47: 'application/exi',
               50: 'application/json',
               60: 'application/cbor'}
"""A map from CoAP-assigned integral codes to Internet media type descriptions."""

media_types_rev = {v:k for k, v in media_types.items()}


class Message(object):
    """A CoAP Message."""

    def __init__(self, mtype=None, mid=None, code=EMPTY, payload=b'', token=b''):
        self.version = 1
        self.mtype = mtype
        self.mid = mid
        self.code = code
        self.token = token
        self.payload = payload
        self.opt = Options()

        self.response_type = None
        self.remote = None
        self.prepath = None
        self.postpath = None

        if self.payload is None:
            raise TypeError("Payload must not be None. Use empty string instead.")

    @classmethod
    def decode(cls, rawdata, remote=None, protocol=None):
        """Create Message object from binary representation of message."""
        (vttkl, code, mid) = struct.unpack('!BBH', rawdata[:4])
        version = (vttkl & 0xC0) >> 6
        if version is not 1:
            raise ValueError("Fatal Error: Protocol Version must be 1")
        mtype = (vttkl & 0x30) >> 4
        token_length = (vttkl & 0x0F)
        msg = Message(mtype=mtype, mid=mid, code=code)
        msg.token = rawdata[4:4 + token_length]
        msg.payload = msg.opt.decode(rawdata[4 + token_length:])
        msg.remote = remote
        msg.protocol = protocol
        return msg

    def encode(self):
        """Create binary representation of message from Message object."""
        if self.mtype is None or self.mid is None:
            raise TypeError("Fatal Error: Message Type and Message ID must not be None.")
        rawdata = six.int2byte((self.version << 6) + ((self.mtype & 0x03) << 4) + (len(self.token) & 0x0F))
        rawdata += struct.pack('!BH', self.code, self.mid)
        rawdata += self.token
        rawdata += self.opt.encode()
        if len(self.payload) > 0:
            rawdata += six.int2byte(0xFF)
            rawdata += self.payload
        return rawdata

    def extractBlock(self, number, size_exp):
        """Extract block from current message."""
        size = 2 ** (size_exp + 4)
        start = number * size
        if start < len(self.payload):
            end = start + size if start + size < len(self.payload) else len(self.payload)
            block = copy.deepcopy(self)
            block.payload = block.payload[start:end]
            block.mid = None
            more = True if end < len(self.payload) else False
            if isRequest(block.code):
                block.opt.block1 = (number, more, size_exp)
                block.opt.size1 = len(self.payload)
            else:
                block.opt.block2 = (number, more, size_exp)
                block.opt.size2 = len(self.payload)
            return block

    def appendRequestBlock(self, next_block):
        """Append next block to current request message.
           Used when assembling incoming blockwise requests."""
        if isRequest(self.code):
            block1 = next_block.opt.block1
            if block1.block_number * (2 ** (block1.size_exponent + 4)) == len(self.payload):
                self.payload += next_block.payload
                self.opt.block1 = block1
                self.token = next_block.token
                self.mid = next_block.mid
                self.response_type = None
            else:
                raise error.NotImplemented()
        else:
            raise ValueError("Fatal Error: called appendRequestBlock on non-request message!!!")

    def appendResponseBlock(self, next_block):
        """Append next block to current response message.
           Used when assembling incoming blockwise responses."""
        if isResponse(self.code):
            ## @TODO: check etags for consistency
            block2 = next_block.opt.block2
            if block2.block_number * (2 ** (block2.size_exponent + 4)) != len(self.payload):
                raise error.NotImplemented()

            if next_block.opt.etag != self.opt.etag:
                raise error.ResourceChanged()

            self.payload += next_block.payload
            self.opt.block2 = block2
            self.token = next_block.token
            self.mid = next_block.mid
        else:
            raise ValueError("Fatal Error: called appendResponseBlock on non-response message!!!")

    def generateNextBlock2Request(self, response):
        """Generate a request for next response block.
           This method is used by client after receiving
           blockwise response from server with "more" flag set."""
        request = copy.deepcopy(self)
        request.payload = b""
        request.mid = None
        if response.opt.block2.block_number == 0 and response.opt.block2.size_exponent > DEFAULT_BLOCK_SIZE_EXP:
            new_size_exponent = DEFAULT_BLOCK_SIZE_EXP
            new_block_number = 2 ** (response.opt.block2.size_exponent - new_size_exponent)
            request.opt.block2 = (new_block_number, False, new_size_exponent)
        else:
            request.opt.block2 = (response.opt.block2.block_number + 1, False, response.opt.block2.size_exponent)
        request.opt.deleteOption(BLOCK1)
        request.opt.deleteOption(OBSERVE)
        return request

    def generateNextBlock1Response(self):
        """Generate a response to acknowledge incoming request block.
           This method is used by server after receiving
           blockwise request from client with "more" flag set."""
        response = Message(code=CHANGED, token=self.token )
        response.remote = self.remote
        if self.opt.block1.block_number == 0 and self.opt.block1.size_exponent > DEFAULT_BLOCK_SIZE_EXP:
            new_size_exponent = DEFAULT_BLOCK_SIZE_EXP
            response.opt.block1 = (0, True, new_size_exponent)
        else:
            response.opt.block1 = (self.opt.block1.block_number, True, self.opt.block1.size_exponent)
        return response

    def debugString(self):
        """Generate pretty string with message contents for debugging purposes"""
        output = []
        output.append("v:%d " % self.version)
        output.append("t:%s " % types[self.mtype])
        output.append("tkl:%d " % len(self.token))
        output.append("")
        return output

class Options(object):
    """Represent CoAP Header Options."""
    def __init__(self):
        self._options = {}

    def decode(self, rawdata):
        """Decode all options in message from raw binary data."""
        option_number = 0

        while len(rawdata) > 0:
            dllen = struct.unpack('!B', rawdata[:1])[0]
            if dllen == 0xFF:
                return rawdata[1:]
            delta = (dllen & 0xF0) >> 4
            length = (dllen & 0x0F)
            rawdata = rawdata[1:]
            (delta, rawdata) = readExtendedFieldValue(delta, rawdata)
            (length, rawdata) = readExtendedFieldValue(length, rawdata)
            option_number += delta
            option = option_formats.get(option_number, OpaqueOption)(option_number)
            option.decode(rawdata[:length])
            self.addOption(option)
            rawdata = rawdata[length:]
        return ''

    def encode(self):
        """Encode all options in option header into string of bytes."""
        data = []
        current_opt_num = 0
        option_list = self.optionList()
        for option in option_list:
            delta, extended_delta = writeExtendedFieldValue(option.number - current_opt_num)
            length, extended_length = writeExtendedFieldValue(option.length)
            data.append(six.int2byte((((int(delta) & 0x0F) << 4) + (int(length) & 0x0F))))
            data.append(extended_delta)
            data.append(extended_length)
            data.append(option.encode())
            current_opt_num = option.number
        return b"".join(data)

    def addOption(self, option):
        """Add option into option header."""
        self._options.setdefault(option.number, []).append(option)

    def deleteOption(self, number):
        """Delete option from option header."""
        if number in self._options:
            self._options.pop(number)

    def getOption (self, number):
        """Get option with specified number."""
        return self._options.get(number)

    def optionList(self):
        return chain.from_iterable(sorted(self._options.values(), key=lambda x: x[0].number))

    def _setUriPath(self, segments):
        """Convenience setter: Uri-Path option"""
        if isinstance(segments, six.binary_type):
            raise ValueError("URI Path should be passed as a list or tuple of segments")
        self.deleteOption(number=URI_PATH)
        for segment in segments:
            self.addOption(StringOption(number=URI_PATH, value=six.binary_type(segment)))

    def _getUriPath(self):
        """Convenience getter: Uri-Path option"""
        segment_list = []
        uri_path = self.getOption(number=URI_PATH)
        if uri_path is not None:
            for segment in uri_path:
                segment_list.append(segment.value)
        return segment_list

    uri_path = property(_getUriPath, _setUriPath)

    def _setUriQuery(self, segments):
        """Convenience setter: Uri-Query option"""
        if isinstance(segments, six.binary_type):
            raise ValueError("URI Query should be passed as a list or tuple of segments")
        self.deleteOption(number=URI_QUERY)
        for segment in segments:
            self.addOption(StringOption(number=URI_QUERY, value=six.binary_type(segment)))

    def _getUriQuery(self):
        """Convenience getter: Uri-Query option"""
        segment_list = []
        uri_query = self.getOption(number=URI_QUERY)
        if uri_query is not None:
            for segment in uri_query:
                segment_list.append(segment.value)
        return segment_list

    uri_query = property(_getUriQuery, _setUriQuery)

    def _setBlock2(self, block_tuple):
        """Convenience setter: Block2 option"""
        self.deleteOption(number=BLOCK2)
        self.addOption(BlockOption(number=BLOCK2, value=block_tuple))

    def _getBlock2(self):
        """Convenience getter: Block2 option"""
        block2 = self.getOption(number=BLOCK2)
        if block2 is not None:
            return block2[0].value
        else:
            return None

    block2 = property(_getBlock2, _setBlock2)

    def _setBlock1(self, block_tuple):
        """Convenience setter: Block1 option"""
        self.deleteOption(number=BLOCK1)
        self.addOption(BlockOption(number=BLOCK1, value=block_tuple))

    def _getBlock1(self):
        """Convenience getter: Block1 option"""
        block1 = self.getOption(number=BLOCK1)
        if block1 is not None:
            return block1[0].value
        else:
            return None

    block1 = property(_getBlock1, _setBlock1)

    def _setSize1(self, size1):
        """Convenience setter: Size1 option"""
        self.deleteOption(number=SIZE1)
        self.addOption(UintOption(number=SIZE1, value=size1))

    def _getSize1(self):
        """Convenience getter: Size1 option"""
        return self.getOption(number=SIZE1)

    size1 = property(_getSize1, _setSize1)

    def _setSize2(self, size2):
        """Convenience setter: Size2 option"""
        self.deleteOption(number=SIZE2)
        self.addOption(UintOption(number=SIZE2, value=size2))

    def _getSize2(self):
        """Convenience getter: Size2 option"""
        return self.getOption(number=SIZE2)

    size2 = property(_getSize2, _setSize2)

    def _setContentFormat(self, content_format):
        """Convenience setter: Content-Format option"""
        self.deleteOption(number=CONTENT_FORMAT)
        self.addOption(UintOption(number=CONTENT_FORMAT, value=content_format))

    def _getContentFormat(self):
        """Convenience getter: Content-Format option"""
        content_format = self.getOption(number=CONTENT_FORMAT)
        if content_format is not None:
            return content_format[0].value
        else:
            return None

    content_format = property(_getContentFormat, _setContentFormat)

    def _setETag(self, etag):
        """Convenience setter: ETag option"""
        self.deleteOption(number=ETAG)
        if etag is not None:
            self.addOption(OpaqueOption(number=ETAG, value=etag))

    def _getETag(self):
        """Convenience getter: ETag option"""
        etag = self.getOption(number=ETAG)
        if etag is not None:
            return etag[0].value
        else:
            return None

    etag = property(_getETag, _setETag, None, "Access to a single ETag on the message (as used in responses)")

    def _setETags(self, etags):
        self.deleteOption(number=ETAG)
        for tag in etags:
            self.addOption(OpaqueOption(number=ETAG, value=tag))

    def _getETags(self):
        etag = self.getOption(number=ETAG)
        return [] if etag is None else [tag.value for tag in etag]

    etags = property(_getETags, _setETags, None, "Access to a list of ETags on the message (as used in requests)")

    def _setObserve(self, observe):
        self.deleteOption(number=OBSERVE)
        if observe is not None:
            self.addOption(UintOption(number=OBSERVE, value=observe))

    def _getObserve(self):
        observe = self.getOption(number=OBSERVE)
        if observe is not None:
            return observe[0].value
        else:
            return None

    observe = property(_getObserve, _setObserve)

    def _setAccept(self, accept):
        self.deleteOption(number=ACCEPT)
        if accept is not None:
            self.addOption(UintOption(number=ACCEPT, value=accept))

    def _getAccept(self):
        accept = self.getOption(number=ACCEPT)
        if accept is not None:
            return accept[0].value
        else:
            return None

    accept = property(_getAccept, _setAccept)

    def _setLocationPath(self, segments):
        """Convenience setter: Location-Path option"""
        if isinstance(segments, six.binary_type):
            raise ValueError("Location Path should be passed as a list or tuple of segments")
        self.deleteOption(number=LOCATION_PATH)
        for segment in segments:
            self.addOption(StringOption(number=LOCATION_PATH, value=six.binary_type(segment)))

    def _getLocationPath(self):
        """Convenience getter: Location-Path option"""
        segment_list = []
        location_path = self.getOption(number=LOCATION_PATH)
        if location_path is not None:
            for segment in location_path:
                segment_list.append(segment.value)
        return segment_list

    location_path = property(_getLocationPath, _setLocationPath)

def readExtendedFieldValue(value, rawdata):
    """Used to decode large values of option delta and option length
       from raw binary form."""
    if value >= 0 and value < 13:
        return (value, rawdata)
    elif value == 13:
        return (struct.unpack('!B', rawdata[:1])[0] + 13, rawdata[1:])
    elif value == 14:
        return (struct.unpack('!H', rawdata[:2])[0] + 269, rawdata[2:])
    else:
        raise ValueError("Value out of range.")


def writeExtendedFieldValue(value):
    """Used to encode large values of option delta and option length
       into raw binary form.
       In CoAP option delta and length can be represented by a variable
       number of bytes depending on the value."""
    if value >= 0 and value < 13:
        return (value, b'')
    elif value >= 13 and value < 269:
        return (13, struct.pack('!B', value - 13))
    elif value >= 269 and value < 65804:
        return (14, struct.pack('!H', value - 269))
    else:
        raise ValueError("Value out of range.")


class OpaqueOption(object):
    """Opaque CoAP option - used to represent opaque options.
       This is a default option type."""

    def __init__(self, number, value=""):
        self.value = value
        self.number = number

    def encode(self):
        rawdata = self.value
        return rawdata

    def decode(self, rawdata):
        self.value = rawdata  # if rawdata is not None else ""

    def _length(self):
        return len(self.value)
    length = property(_length)


class StringOption(object):
    """String CoAP option - used to represent string options."""

    def __init__(self, number, value=""):
        self.value = value
        self.number = number

    def encode(self):
        rawdata = self.value
        return rawdata

    def decode(self, rawdata):
        self.value = rawdata  # if rawdata is not None else ""

    def _length(self):
        return len(self.value)
    length = property(_length)


class UintOption(object):
    """Uint CoAP option - used to represent uint options."""

    def __init__(self, number, value=0):
        self.value = value
        self.number = number

    def encode(self):
        rawdata = struct.pack("!L", self.value)
        return rawdata.lstrip(six.int2byte(0))

    def decode(self, rawdata):
        value = 0
        for byte in six.iterbytes(rawdata):
            value = (value * 256) + byte
        self.value = value
        return self

    def _length(self):
        if self.value > 0:
            return (self.value.bit_length() - 1) // 8 + 1
        else:
            return 0
    length = property(_length)


class BlockOption(object):
    """Block CoAP option - special option used only for Block1 and Block2 options.
       Currently it is the only type of CoAP options that has
       internal structure."""
    BlockwiseTuple = collections.namedtuple('BlockwiseTuple', ['block_number', 'more', 'size_exponent'])

    def __init__(self, number, value=(0, None, 0)):
        self.value = self.BlockwiseTuple._make(value)
        self.number = number

    def encode(self):
        as_integer = (self.value[0] << 4) + (self.value[1] * 0x08) + self.value[2]
        rawdata = struct.pack("!L", as_integer)
        return rawdata.lstrip(six.int2byte(0))

    def decode(self, rawdata):
        as_integer = 0
        for byte in six.iterbytes(rawdata):
            as_integer = (as_integer * 256) + byte
        self.value = self.BlockwiseTuple(block_number=(as_integer >> 4), more=bool(as_integer & 0x08), size_exponent=(as_integer & 0x07))

    def _length(self):
        return ((self.value[0].bit_length() + 3) / 8 + 1)
    length = property(_length)

option_formats = {3:  StringOption,
                  6:  UintOption,
                  7:  UintOption,
                  8:  StringOption,
                  11: StringOption,
                  12: UintOption,
                  14: UintOption,
                  15: StringOption,
                  16: UintOption,
                  20: StringOption,
                  23: BlockOption,
                  27: BlockOption,
                  28: UintOption,
                  35: StringOption,
                  39: StringOption,
                  60: UintOption}
"""Dictionary used to assign option type to option numbers."""


def isRequest(code):
    return True if (code >= 1 and code < 32) else False


def isResponse(code):
    return True if (code >= 64 and code < 192) else False


def isSuccessful(code):
    return True if (code >= 64 and code < 96) else False


def uriPathAsString(segment_list):
    return b'/' + b'/'.join(segment_list)


class Coap(protocol.DatagramProtocol):

    def __init__(self, endpoint):
        """Initialize a CoAP protocol instance."""
        self.message_id = random.randint(0, 65535)
        self.token = random.randint(0, 65535)
        self.endpoint = endpoint
        self.recent_local_ids = {}  # recently received messages with IDs generated locally (identified by message ID and remote)
        self.recent_remote_ids = {}  # recently received messages with IDs generated by remote endpoints (identified by message ID and remote)
        self.active_exchanges = {}  # active exchanges i.e. sent CON messages (identified by message ID and remote)
        self.outgoing_requests = {}  # unfinished outgoing requests (identified by token and remote)
        self.incoming_requests = {}  # unfinished incoming requests (identified by URL path and remote)
        self.observations = {} # outgoing observations. (token, remote) -> callback

    def datagramReceived(self, data, remote):
        host, port = remote
        log.msg("Received %r from %s:%d" % (data, host, port))
        message = Message.decode(data, (ip_address(unicode(host)), port), self)
        if self.deduplicateMessage(message) is True:
            return
        if isRequest(message.code):
            self.processRequest(message)
        elif isResponse(message.code):
            self.processResponse(message)
        elif message.code is EMPTY:
            self.processEmpty(message)

    def deduplicateMessage(self, message):
        """Check incoming message if it's a duplicate.

           Duplicate is a message with the same Message ID (mid)
           and sender (remote), as message received within last
           EXCHANGE_LIFETIME seconds (usually 247 seconds)."""

        def addMessageToRecent(cache, key):
            expiration = reactor.callLater(EXCHANGE_LIFETIME, removeMessageFromRecent, cache, key)
            cache[key] = (message, expiration)

        def removeMessageFromRecent(cache, key):
            cache.pop(key)

        key = (message.mid, message.remote)
        log.msg("Incoming Message ID: %d" % message.mid)
        if message.mtype in (CON, NON):
            if key in self.recent_remote_ids:
                if message.mtype is CON:
                    if len(self.recent_remote_ids[key]) == 3:
                        log.msg('Duplicate CON received, sending old response again')
                        self.sendMessage(self.recent_remote_ids[key][2])
                    else:
                        log.msg('Duplicate CON received, no response to send')
                else:
                    log.msg('Duplicate NON received')
                return True
            else:
                log.msg('New unique CON or NON message received')
                addMessageToRecent(self.recent_remote_ids, key)
                return False
        else:
            if key in self.recent_local_ids:
                log.msg('Duplicate ACK or RST received')
                return True
            else:
                log.msg('New unique ACK or RST message received')
                addMessageToRecent(self.recent_local_ids, key)
                return False

    def processResponse(self, response):
        """Method used for incoming response processing."""

        def resetUnrecognized():
            log.msg("Response not recognized - sending RST.")
            rst = Message(mtype=RST, mid=response.mid, code=EMPTY, payload='')
            rst.remote = response.remote
            self.sendMessage(rst)
        
        def ackIfConfirmable():
            if response.mtype is CON:
                ack = Message(mtype=ACK, mid=response.mid, code=EMPTY, payload="")
                ack.remote = response.remote
                self.sendMessage(ack)

        if response.mtype is RST:
            return
        if response.mtype is ACK:
            if response.mid in self.active_exchanges:
                self.removeExchange(response)
            else:
                return
        log.msg("Received Response, token: %s, host: %s, port: %s" % (codecs.encode(response.token, 'hex'), response.remote[0], response.remote[1]))
        if (response.token, response.remote) in self.outgoing_requests:
            self.outgoing_requests.pop((response.token, response.remote)).handleResponse(response)
            ackIfConfirmable()

        elif (response.token, response.remote) in self.observations:
            ## @TODO: deduplication based on observe option value
            callback_tuple, original_request_uri_path = self.observations[(response.token, response.remote)]
            callback, args, kw = callback_tuple
            args = args or ()
            kw = kw or {}

            block2 = response.opt.block2
            if block2 is None:
                ackIfConfirmable()
                callback(response, *args, **kw)
            elif block2.block_number == 0:
                ackIfConfirmable()
                if block2.more is False:
                    callback(response, *args, **kw)
                else:
                    request = Message(code=GET)
                    request.opt.uri_path = original_request_uri_path
                    request.remote = response.remote
                    request = request.generateNextBlock2Request(response)
                    requester = Requester(response.protocol, request, None, None, None,
                                          None, None, None,
                                          None, None, None)

                    requester.assembled_response = response
                    d = requester.deferred
                    d.addCallback( callback, *args, **kw)
            else:
                resetUnrecognized()

            if response.opt.observe is None:
                del self.observations[(response.token, response.remote)]
        else:
            resetUnrecognized()


    def processRequest(self, request):
        """Method used for incoming request processing."""
        if request.mtype not in (CON, NON):
            response = Message(code=BAD_REQUEST, payload='Wrong message type for request!')
            self.respond(response, request)
            return
        if (uriPathAsString(request.opt.uri_path), request.remote) in self.incoming_requests:
            log.msg("Request pertains to earlier blockwise requests.")
            self.incoming_requests.pop((uriPathAsString(request.opt.uri_path), request.remote)).handleNextRequest(request)
        else:
            responder = Responder(self, request)

    def processEmpty(self, message):
        if message.mtype is CON:
            log.msg('Empty CON message received (CoAP Ping) - replying with RST.')
            rst = Message(mtype=RST, mid=message.mid, code=EMPTY, payload='')
            rst.remote = message.remote
            self.sendMessage(rst)
        #TODO: passing ACK/RESET info to application
        #Currently it doesn't matter if empty ACK or RST is received - in both cases exchange has to be removed
        if message.mid in self.active_exchanges and message.mtype in (ACK, RST):
            self.removeExchange(message)

    def sendMessage(self, message):
        """Set Message ID, encode and send message.
           Also if message is Confirmable (CON) add Exchange"""
        address, port = message.remote
        host = str(address)
        target = (host, port)
        log.msg("Sending message to %s:%d" % (host, port))
        recent_key = (message.mid, message.remote)
        if recent_key in self.recent_remote_ids:
            if len(self.recent_remote_ids[recent_key]) != 3:
                self.recent_remote_ids[recent_key] = self.recent_remote_ids[recent_key] + (message,)

        if message.mid is None:
            message.mid = self.nextMessageID()
        msg = message.encode()
        self.transport.write(msg, target)
        if message.mtype is CON:
            self.addExchange(message)
        log.msg("Message %r sent successfully" % msg)

    def nextMessageID(self):
        """Reserve and return a new message ID."""
        message_id = self.message_id
        self.message_id = 0xFFFF & (1 + self.message_id)
        return message_id

    def nextToken(self):
        """Reserve and return a new Token for request."""
        #TODO: add proper Token handling
        token = self.token
        self.token = (self.token + 1) & 0xffffffffffffffff
        return codecs.decode((b"%08x" % self.token), "hex")

    def addExchange(self, message):
        """Add an "exchange" for outgoing CON message.

           CON (Confirmable) messages are automatically
           retransmitted by protocol until ACK or RST message
           with the same Message ID is received from target host."""

        timeout = random.uniform(ACK_TIMEOUT, ACK_TIMEOUT * ACK_RANDOM_FACTOR)
        retransmission_counter = 0
        next_retransmission = reactor.callLater(timeout, self.retransmit, message, timeout, retransmission_counter)
        self.active_exchanges[message.mid] = (message, next_retransmission)
        log.msg("Exchange added, Message ID: %d." % message.mid)

    def removeExchange(self, message):
        """Remove exchange from active exchanges and cancel the timeout
           to next retransmission."""
        self.active_exchanges.pop(message.mid)[1].cancel()
        log.msg("Exchange removed, Message ID: %d." % message.mid)

    def retransmit(self, message, timeout, retransmission_counter):
        """Retransmit CON message that has not been ACKed or RSTed."""
        self.active_exchanges.pop(message.mid)
        if retransmission_counter < MAX_RETRANSMIT:
            address, port = message.remote
            host = str(address)
            target = (host, port)
            self.transport.write(message.encode(), target)
            retransmission_counter += 1
            timeout *= 2
            next_retransmission = reactor.callLater(timeout, self.retransmit, message, timeout, retransmission_counter)
            self.active_exchanges[message.mid] = (message, next_retransmission)
            log.msg("Retransmission, Message ID: %d." % message.mid)
        else:
            pass
            #TODO: error handling (especially for requests)

    def request(self, request, observeCallback=None, block1Callback=None, block2Callback=None,
                observeCallbackArgs=None, block1CallbackArgs=None, block2CallbackArgs=None,
                observeCallbackKeywords=None, block1CallbackKeywords=None, block2CallbackKeywords=None):
        """Send a request.

           This is a method that should be called by user app."""
        return Requester(self, request, observeCallback, block1Callback, block2Callback,
                         observeCallbackArgs, block1CallbackArgs, block2CallbackArgs,
                         observeCallbackKeywords, block1CallbackKeywords, block2CallbackKeywords).deferred


class Requester(object):
    """Class used to handle single outgoing request.

       Class includes methods that handle sending
       outgoing blockwise requests and receiving incoming
       blockwise responses."""

    def __init__(self, protocol, app_request, observeCallback, block1Callback, block2Callback,
                       observeCallbackArgs, block1CallbackArgs, block2CallbackArgs,
                       observeCallbackKeywords, block1CallbackKeywords, block2CallbackKeywords):
        self.protocol = protocol
        self.app_request = app_request
        self.assembled_response = None
        assert observeCallback == None or callable(observeCallback)
        assert block1Callback == None or callable(block1Callback)
        assert block2Callback == None or callable(block2Callback)
        self.cbs = ((observeCallback, observeCallbackArgs, observeCallbackKeywords),
                    (block1Callback, block1CallbackArgs, block1CallbackKeywords),
                    (block2Callback, block2CallbackArgs, block2CallbackKeywords))
        if isRequest(self.app_request.code) is False:
            raise ValueError("Message code is not valid for request")
        size_exp = DEFAULT_BLOCK_SIZE_EXP
        if len(self.app_request.payload) > (2 ** (size_exp + 4)):
            request = self.app_request.extractBlock(0, size_exp)
            self.app_request.opt.block1 = request.opt.block1
        else:
            request = self.app_request
        if request is None:
            return defer.fail()
        self.deferred = self.sendRequest(request)
        self.deferred.addCallback(self.processBlock1InResponse)
        self.deferred.addCallback(self.processBlock2InResponse)

    def sendRequest(self, request):
        """Send a request or single request block.

           This method is used in 3 situations:
           - sending non-blockwise request
           - sending blockwise (Block1) request block
           - asking server to send blockwise (Block2) response block
        """

        def cancelRequest(d):
            """Clean request after cancellation from user application."""

            log.msg("Request cancelled")
            self.protocol.outgoing_requests.pop((request.token, request.remote))

        def timeoutRequest(d):
            """Clean the Request after a timeout."""

            log.msg("Request timed out")
            del self.protocol.outgoing_requests[(request.token, request.remote)]
            d.errback(error.RequestTimedOut())

        def gotResult(result):
            if timeout.active():
                timeout.cancel()
            return result

        if request.mtype is None:
            request.mtype = CON
        request.token = self.protocol.nextToken()
        try:
            self.protocol.sendMessage(request)
        except:
            return defer.fail()
        else:
            d = defer.Deferred(cancelRequest)
            timeout = reactor.callLater(REQUEST_TIMEOUT, timeoutRequest, d)
            d.addBoth(gotResult)
            self.protocol.outgoing_requests[(request.token, request.remote)] = self
            log.msg("Sending request - Token: %s, Host: %s, Port: %s" % (codecs.encode(request.token, 'hex'), str(request.remote[0]), request.remote[1]))
            if request.opt.observe is not None and self.cbs[0][0] is not None:
                d.addCallback(self.registerObservation, self.cbs[0], request.opt.uri_path)
            return d

    def handleResponse(self, response):
        d, self.deferred = self.deferred, None
        d.callback(response)

    def registerObservation(self, response, callback, request_uri_path):
        if response.opt.observe is not None:
            self.protocol.observations[(response.token, response.remote)] = (callback, request_uri_path)
        return response

    def processBlock1InResponse(self, response):
        """Process incoming response with regard to Block1 option.

           Method is called for all responses, with or without Block1
           option.

           Method is recursive - calls itself until all request blocks
           are sent."""

        if response.opt.block1 is not None:
            block1 = response.opt.block1
            log.msg("Response with Block1 option received, number = %d, more = %d, size_exp = %d." % (block1.block_number, block1.more, block1.size_exponent))
            if block1.block_number == self.app_request.opt.block1.block_number:
                if block1.size_exponent < self.app_request.opt.block1.size_exponent:
                    next_number = (self.app_request.opt.block1.block_number + 1) * 2 ** (self.app_request.opt.block1.size_exponent - block1.size_exponent)
                    next_block = self.app_request.extractBlock(next_number, block1.size_exponent)
                else:
                    next_block = self.app_request.extractBlock(self.app_request.opt.block1.block_number + 1, block1.size_exponent)
                if next_block is not None:
                    if block1.more is False:
                        if response.code not in (CREATED, DELETED, VALID, CHANGED, CONTENT, CONTINUE):
                            log.msg("Client returned non 2.xx response to intermediate block, code = %d." % (response.code))
                            return defer.fail()
                    self.app_request.opt.block1 = next_block.opt.block1
                    block1Callback, args, kw = self.cbs[1]
                    if block1Callback is None:
                        return self.sendNextRequestBlock(None, next_block)
                    else:
                        args = args or ()
                        kw = kw or {}
                        d = block1Callback(response, *args, **kw)
                        d.addCallback(self.sendNextRequestBlock, next_block)
                        return d
                else:
                    if block1.more is False:
                        return defer.succeed(response)
                    else:
                        return defer.fail()
            else:
                return defer.fail()
        else:
            if self.app_request.opt.block1 is None:
                return defer.succeed(response)
            else:
                return defer.fail()

    def sendNextRequestBlock(self, result, next_block):
        """Helper method used for sending request blocks."""
        log.msg("Sending next block of blockwise request.")
        self.deferred = self.sendRequest(next_block)
        self.deferred.addCallback(self.processBlock1InResponse)
        return self.deferred

    def processBlock2InResponse(self, response):
        """Process incoming response with regard to Block2 option.

           Method is called for all responses, with or without Block2
           option.

           Method is recursive - calls itself until all response blocks
           from server are received."""
        if response.opt.block2 is not None:
            block2 = response.opt.block2
            log.msg("Response with Block2 option received, number = %d, more = %d, size_exp = %d." % (block2.block_number, block2.more, block2.size_exponent))
            if self.assembled_response is not None:
                try:
                    self.assembled_response.appendResponseBlock(response)
                except error.Error as e:
                    return defer.fail(e)
            else:
                if block2.block_number is 0:
                    log.msg("Receiving blockwise response")
                    self.assembled_response = response
                else:
                    log.msg("ProcessBlock2 error: transfer started with nonzero block number.")
                    return defer.fail()
            if block2.more is True:
                request = self.app_request.generateNextBlock2Request(response)
                block2Callback, args, kw = self.cbs[2]
                if block2Callback is None:
                    return self.askForNextResponseBlock(None, request)
                else:
                    args = args or ()
                    kw = kw or {}
                    d = block2Callback(response, *args, **kw)
                    d.addCallback(self.askForNextResponseBlock, request)
                    return d
            else:
                return defer.succeed(self.assembled_response)
        else:
            if self.assembled_response is None:
                return defer.succeed(response)
            else:
                return defer.fail(error.MissingBlock2Option)

    def askForNextResponseBlock(self, result, request):
        """Helper method used to ask server to send next response block."""
        log.msg("Requesting next block of blockwise response.")
        self.deferred = self.sendRequest(request)
        self.deferred.addCallback(self.processBlock2InResponse)
        return self.deferred




class Responder(object):
    """Class used to handle single incoming request.

       Class includes methods that handle receiving
       incoming blockwise requests, searching for target
       resources, preparing responses and sending outgoing
       blockwise responses.
       """

    def __init__(self, protocol, request):
        self.protocol = protocol
        self.assembled_request = None
        self.app_response = None
        log.msg("Request doesn't pertain to earlier blockwise requests.")
        self.deferred = self.processBlock1InRequest(request)
        self.deferred.addErrback(self.handleBlock1RequestErrors)
        self.deferred.addCallback(self.dispatchRequest)

    def processBlock1InRequest(self, request):
        """Process incoming request with regard to Block1 option.

           Method is recursive - calls itself until all request blocks
           are received."""
        if request.opt.block1 is not None:
            block1 = request.opt.block1
            log.msg("Request with Block1 option received, number = %d, more = %d, size_exp = %d." % (block1.block_number, block1.more, block1.size_exponent))
            if block1.block_number == 0:
                #TODO: Check if resource is available - if not send error immediately
                #TODO: Check if method is allowed - if not send error immediately
                log.msg("New or restarted incoming blockwise request.")
                self.assembled_request = request
            else:
                try:
                    self.assembled_request.appendRequestBlock(request)
                except (error.NotImplemented, AttributeError):
                    self.respondWithError(request, NOT_IMPLEMENTED, b"Error: Request block received out of order!")
                    return defer.fail(error.NotImplemented())
                    #raise error.NotImplemented
            if block1.more is True:
                #TODO: SUCCES_CODE Code should be either Changed or Created - Resource check needed
                #TODO: SIZE_CHECK1 should check if the size of incoming payload is still acceptable
                #TODO: SIZE_CHECK2 should check if Size option is present, and reject the resource if size too large
                return self.acknowledgeRequestBlock(request)
            else:
                log.msg("Complete blockwise request received.")
                return defer.succeed(self.assembled_request)
        else:
            if self.assembled_request is not None:
                log.msg("Non-blockwise request received during blockwise transfer. Blockwise transfer cancelled.")
            return defer.succeed(request)

    def acknowledgeRequestBlock(self, request):
        """Helper method used to ask client to send next request block."""
        log.msg("Sending block acknowledgement (allowing client to send next block).")
        response = request.generateNextBlock1Response()
        self.deferred = self.sendNonFinalResponse(response, request)
        self.deferred.addCallback(self.processBlock1InRequest)
        return self.deferred

    def dispatchRequest(self, request):
        """Dispatch incoming request - search endpoint
           resource tree for resource in Uri Path
           and call proper CoAP Method on it."""
        #TODO: Request with Block2 option and non-zero block number should get error response
        request.prepath = []
        request.postpath = request.opt.uri_path
        try:
            resource = self.protocol.endpoint.getResourceFor(request)
            d = resource.render(request)
        except error.NoResource:
            self.respondWithError(request, NOT_FOUND, b"Error: Resource not found!")
        except error.UnallowedMethod:
            self.respondWithError(request, METHOD_NOT_ALLOWED, b"Error: Method not allowed!")
        except error.UnsupportedMethod:
            self.respondWithError(request, METHOD_NOT_ALLOWED, b"Error: Method not recognized!")
        else:
            delayed_ack = reactor.callLater(EMPTY_ACK_DELAY, self.sendEmptyAck, request)
            if resource.observable and request.code == GET and request.opt.observe is not None:
                d.addCallback(self.handleObserve, request, resource)
            d.addCallback(self.respond, request, delayed_ack)
            return d

    def handleBlock1RequestErrors(self, err):
        """Handle (silently ignore) request errors related
           to Block1. Currently it's used to catch:
           - NotImplemented - requests which are send non-sequentially
           - WaitingForClientTimedOut - requests timed out
        """
        err.trap(error.NotImplemented, error.WaitingForClientTimedOut)

    def respondWithError(self, request, code, payload):
        """Helper method to send error response to client."""
        log.msg(payload)
        response = Message(code=code, payload=payload)
        self.respond(response, request)
        return

    def handleObserve(self, app_response, request, resource):
        """Intermediate state of sending a response that the response will go
        through if it might need to be processed for observation. This both
        handles the implications for notification sending and adds the observe
        response option."""

        observation_identifier = (request.remote, request.token)

        if app_response.code not in (VALID, CONTENT):
            if observation_identifier in resource.observers:
                ## @TODO cancel observation
                pass

            return app_response

        if observation_identifier in resource.observers:
            pass ## @TODO renew that observation (but keep in mind that whenever we send a notification, the original message is replayed)
        else:
            obs = Observation(request)
            resource.observers[observation_identifier] = obs

        app_response.opt.observe = resource.observe_index

        return app_response


    def respond(self, app_response, request, delayed_ack=None):
        """Take application-supplied response and prepare it
           for sending."""

        log.msg("Preparing response...")
        if delayed_ack is not None:
            if delayed_ack.active() is True:
                delayed_ack.cancel()
        self.app_response = app_response
        size_exp = min(request.opt.block2.size_exponent if request.opt.block2 is not None else DEFAULT_BLOCK_SIZE_EXP, DEFAULT_BLOCK_SIZE_EXP)
        if len(self.app_response.payload) > (2 ** (size_exp + 4)):
            response = self.app_response.extractBlock(0, size_exp)
            self.app_response.opt.block2 = response.opt.block2
            return self.sendResponseBlock(response, request)
        else:
            self.sendResponse(app_response, request)
            return defer.succeed(None)
        if response is None:
            return defer.fail()

    def processBlock2InRequest(self, request):
        """Process incoming request with regard to Block2 option.

           Method is recursive - calls itself until all response blocks
           are sent to client."""
        if request.opt.block2 is not None:
            block2 = request.opt.block2
            log.msg("Request with Block2 option received, number = %d, more = %d, size_exp = %d." % (block2.block_number, block2.more, block2.size_exponent))
            sent_length = (2 ** (self.app_response.opt.block2.size_exponent + 4)) * (self.app_response.opt.block2.block_number + 1)
            #TODO: compare block size of request and response - calculate new block_number if necessary
            if (2 ** (block2.size_exponent + 4)) * block2.block_number == sent_length:
                next_block = self.app_response.extractBlock(block2.block_number, block2.size_exponent)
                if next_block is None:
                    log.msg("Block out of range")
                    return defer.fail()
                if next_block.opt.block2.more is True:
                    self.app_response.opt.block2 = next_block.opt.block2
                    return self.sendResponseBlock(next_block, request)
                else:
                    self.sendResponse(next_block, request)
                    return defer.succeed(None)
            else:
                log.msg("Incorrect block number requested")
                return defer.fail()
        else:
            return defer.fail()

    def sendResponseBlock(self, response_block, request):
        """Helper method to send next response block to client."""
        log.msg("Sending response block.")
        self.deferred = self.sendNonFinalResponse(response_block, request)
        self.deferred.addCallback(self.processBlock2InRequest)
        self.deferred.addErrback(self.handleBlock2RequestErrors)
        return self.deferred

    def handleBlock2RequestErrors(self, err):
        """Handle (silently ignore) request errors related
           to Block2. Currently it's used only to ignore
           when client doesn't request next block for a long time"""
        err.trap(error.WaitingForClientTimedOut)

    def sendNonFinalResponse(self, response, request):
        """Helper method to send, a response to client, and setup
           a timeout for client."""

        def cancelNonFinalResponse(d):
            log.msg("Waiting for next client request cancelled")
            self.protocol.incoming_requests.pop((uriPathAsString(request.opt.uri_path), request.remote))

        def timeoutNonFinalResponse(d):
            """Clean the Response after a timeout."""

            log.msg("Waiting for next blockwise request timed out")
            self.protocol.incoming_requests.pop((uriPathAsString(request.opt.uri_path), request.remote))
            d.errback(error.WaitingForClientTimedOut())

        def gotResult(result):
            if timeout.active():
                timeout.cancel()
            return result

        d = defer.Deferred(cancelNonFinalResponse)
        timeout = reactor.callLater(MAX_TRANSMIT_WAIT, timeoutNonFinalResponse, d)
        d.addBoth(gotResult)
        self.protocol.incoming_requests[(uriPathAsString(request.opt.uri_path), request.remote)] = self
        self.sendResponse(response, request)
        return d

    def handleNextRequest(self, request):
        d, self.deferred = self.deferred, None
        d.callback(request)

    def sendResponse(self, response, request):
        """Send a response or single response block.

           This method is used in 4 situations:
           - sending success non-blockwise response
           - asking client to send blockwise (Block1) request block
           - sending blockwise (Block2) response block
           - sending any error response
        """
        #if isResponse(response.code) is False:
            #raise ValueError("Message code is not valid for a response.")
        response.token = request.token
        log.msg("Token: %s" % ":".join(("{:02x}".format(c) for c in six.iterbytes(response.token))))
        response.remote = request.remote
        if request.opt.block1 is not None:
            response.opt.block1 = request.opt.block1
        if response.mtype is None:
            if request.response_type is None:
                if request.mtype is CON:
                    response.mtype = ACK
                else:
                    response.mtype = NON
            elif request.response_type is ACK:
                response.mtype = CON
            else:
                raise Exception()
        request.response_type = response.mtype
        if response.mid is None:
            if response.mtype in (ACK, RST):
                response.mid = request.mid
        log.msg("Sending response, type = %s (request type = %s)" % (types[response.mtype], types[request.mtype]))
        self.protocol.sendMessage(response)

    def sendEmptyAck(self, request):
        """Send separate empty ACK when response preparation takes too long."""
        log.msg("Response preparation takes too long - sending empty ACK.")
        ack = Message(mtype=ACK, code=EMPTY, payload="")
        self.respond(ack, request)

class Observation(object):
    """An active CoAP observation is described as an Observation object
    attached to a Resource in .observers[(address, token)].

    It keeps a complete copy of the original request for simplicity (while it
    actually would only need parts of that request, like the accept option)."""

    def __init__(self, original_request):
        self.original_request = original_request

    def trigger(self):
        # bypassing parsing and duplicate detection, pretend the request came in again
        log.msg("Triggering retransmission with original request %r (will set response_type to ACK)" % vars(self.original_request))
        self.original_request.response_type = ACK # trick responder into sending CON
        Responder(self.original_request.protocol, self.original_request)
        ## @TODO pass a callback down to the exchange -- if it gets a RST, we have to unregister
