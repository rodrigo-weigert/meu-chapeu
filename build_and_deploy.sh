#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
TAG=$(git rev-parse --short HEAD)

cd "$SCRIPT_DIR"

source ./deploy.env

echo "Building image $IMAGE_NAME..."
docker build -t "$IMAGE_NAME:$TAG" -t "$IMAGE_NAME:latest" .

echo "Saving image $IMAGE_NAME to $IMAGE_PATH..."
docker save -o "$IMAGE_PATH" "$IMAGE_NAME:$TAG" "$IMAGE_NAME:latest"

echo "Uploading image and .env to remote host..."
scp "$IMAGE_PATH" "${REMOTE_USER}@${REMOTE_HOST}:$IMAGE_PATH"
scp .env "${REMOTE_USER}@${REMOTE_HOST}:$ENV_PATH"

ssh -q "${REMOTE_USER}@${REMOTE_HOST}" <<EOF
set -e

echo "Stopping and removing container $CONTAINER_NAME..."
docker stop -s SIGINT -t 20 $CONTAINER_NAME || true
docker rm $CONTAINER_NAME || true

echo "Loading image $IMAGE_PATH..."
docker load < $IMAGE_PATH

echo "Starting container..."
docker run -d --name $CONTAINER_NAME --env-file $ENV_PATH --restart unless-stopped -v $LOGS_PATH:/bot/logs $IMAGE_NAME:$TAG
EOF
