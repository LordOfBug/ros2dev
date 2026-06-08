#!/bin/bash
echo "Building ros2dev:latest ..."
docker build -f Dockerfile . -t ros2dev:latest
echo "Done!"
