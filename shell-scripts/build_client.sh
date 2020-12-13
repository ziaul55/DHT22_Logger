#!/bin/sh

# Build client as described on Dockerfile_client
docker build --tag txthings_dht_client --file Dockerfile_client ../
