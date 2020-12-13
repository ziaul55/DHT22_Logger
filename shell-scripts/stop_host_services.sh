#!/bin/sh

# stop influxdb & grafana-server
# requring sudo privilege
# ------------------------------

# with serice command
service influxdb stop
service grafana-server stop

# with systemctl command
#systemctl stop influxdb 
#systemctl stop grafana-server 
