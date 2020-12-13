#!/bin/sh

# check status of influxdb & grafana-server
# -----------------------------------------

# with serice command
service influxdb status
service grafana-server status

# with systemctl command
#systemctl status influxdb 
#systemctl status grafana-server 
