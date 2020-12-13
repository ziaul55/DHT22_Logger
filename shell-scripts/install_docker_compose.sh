#!/bin/sh

apt-get update
apt-get install docker docker-compose
usermod -aG docker $USER
