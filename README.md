# Introduction
- In this project we have sensed temperature and humidity data using DHT22 and stored the sensed data into InfluxDB and then visualized in Grafana. 
- We built this project by implementing _CoAP_ prototol with _txThings_ framework using Python 2.

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
docker-compose up
```
