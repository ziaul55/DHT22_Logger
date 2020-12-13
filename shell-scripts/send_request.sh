#!/bin/sh

# help:
# -----
# coap-client --help

# send request to CoAP server as
# coap://<host>:<port>/sensors/dht/<temperature/humidity>
# -------------------------------------------------------

# temperature
coap-client -m post coap://192.168.1.125:5683/sensors/dht/temperature -e 25.5

# humidity
coap-client -m post coap://192.168.1.125:5683/sensors/dht/humidity -e 30.5
