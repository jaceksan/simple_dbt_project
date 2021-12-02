#!/bin/bash

if [ -z "$1" ]; then
  echo "Usage: $0 <service_name>"
  echo ""
  echo "Use this script for rebuilding statefull services, like postgres."
  exit 1
fi

DC_FILES="-f docker-compose.yml"

docker-compose $DC_FILES rm -fsv "$1"
docker volume rm "$(docker volume ls | grep "${PWD##*/}_$1"-data | awk '{print $2}')"
docker-compose $DC_FILES up -d "$1"
