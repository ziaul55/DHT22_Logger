# Introduction
- In this project we have sensed temperature and humidity data using DHT22 and stored the sensed data into InfluxDB and then visualized in Grafana. 
- We built this project by implementing _CoAP_ protocol with _txThings_ framework using Python 2.

## Requirements

#### Hardware
- Adafruit DHT22 sensor (+ ribbon cables)
- Raspberry Pi 3 (+ power adapter)
- Monitor 

#### Software
- Python 2
- InfluxDB (time series database)
- Grafana (visualization tool)
- Browser

## Configuration
DHT22 sensor read data through the BCM pin 23. Configurations are available at _docker_compose.yml_ and _src/config.py_ files.

## How to run
```
# clone the project
git clone https://github.com/ziaul55/dht22_logger.git

# install docker and docker-compose
sudo su
chmod +x shell-scripts/install_docker_compose.sh
sh shell-scripts/install_docker_compose.sh
exit
[reboot the Raspberry Pi]

# build the project
cd dht22_logger
docker-compose build

# run the project
# stop influxdb and grafana-server if these are already running 
# into the Raspberry Pi with 'sudo service influxdb stop' and 
# 'sudo grafana-server stop'
docker-compose up
```
## Visualization
- We built this project with a single Raspberry Pi 3 having IP address _192.168.1.125_. Visualization is done with _Grafana_ which is running on port _3000_. So, complete _URL_ for _Grafana_ will be _192.168.1.125:3000_. 
- Now browse _192.168.1.125:3000_ URL and provide the username and password as admin admin. Reset password or skip.
- Press on _Gear_ icon to add the _Data Source_. In this project, we configured our _influxdb_ credentials on _docker-compose.yml_ file. So, add an InfluxDB Data Source with following configuration

```
  * HTTP URL: 192.168.1.125:8086
  * InfluxDB Details
    - Database: strawberry_factory
    - User: influxDBuser
    - Password: influxDBpass
  * Press on 'Save & Test'
```
- Press on _+_ icon to add a new panel. Add temperature and humidity with two separate queries and save the panel.
