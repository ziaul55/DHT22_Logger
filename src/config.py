import os



# ------------------------------  from database.py file ------------------------------ # 
# InfluxDB credentials
HOST      = os.environ.get('INFLUXDB_HOST', '192.168.1.125')
PORT      = os.environ.get('INFLUXDB_PORT', 8086)
USERNAME  = os.environ.get('INFLUXDB_USER', 'influxDBuser')
PASSWORD  = os.environ.get('INFLUXDB_USER_PASSWORD', 'influxDBpass')
DATABASE  = os.environ.get('INFLUXDB_DB', 'strawberry_factory')

# measurements/tables
TEMPERATURE = 'temperature'
HUMIDITY    = 'humidity'

# tags/indices
ROOM1  = 'room1'


# ------------------------------  from client.py file ------------------------------ # 
# basic settings
# --------------
SLEEP     = int(os.environ.get("SLEEP", 5))     # sleep time after a reading 

# DHT config
# ----------
MODEL     = int(os.environ.get("DHT_MODEL", 22))    # model -- 11, 22 or 2302
PIN       = int(os.environ.get("DHT_PIN", 23))      # pin   -- BCM data pin header

# CoAP settings
# -------------
CoAP_HOST = os.environ.get("CoAP_HOST", "192.168.1.125")    # CoAP host
#CoAP_HOST=os.environ.get("CoAP_HOST", "localhost")      # CoAP host
CoAP_PORT = int(os.environ.get("CoAP_PORT", 5683))      # CoAP port

