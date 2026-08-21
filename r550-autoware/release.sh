#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

IMAGE_NAME="r550-autoware:latest"

# ── Check that the base image exists ───────────────────────────────────
if ! docker image inspect r550-ros1-bridge:latest >/dev/null 2>&1; then
    echo "Error: r550-ros1-bridge:latest not found."
    echo "Build it first:  cd ../humble-ros1-bride && docker buildx build --platform linux/arm64 -t r550-ros1-bridge:latest ."
    exit 1
fi

# ── Build ──────────────────────────────────────────────────────────────
echo "==> Building $IMAGE_NAME (linux/arm64)..."
docker buildx build \
    --platform linux/arm64 \
    -t "$IMAGE_NAME" \
    --load \
    .

echo "==> Build complete: $IMAGE_NAME"
echo ""
echo "To push to a registry:"
echo "  docker buildx build --platform linux/arm64 -t <registry>/$IMAGE_NAME --push ."
