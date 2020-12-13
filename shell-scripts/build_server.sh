#!/bin/sh

# Build server as described on Dockerfile_server
docker build --tag txthings_dht_server --file Dockerfile_server ../
