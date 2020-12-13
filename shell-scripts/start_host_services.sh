#!/bin/sh

# start influxdb & grafana-server
# requring sudo privilege
# ------------------------------

# with serice command
service influxdb start
service grafana-server start

# with systemctl command
#systemctl start influxdb 
#systemctl start grafana-server 
