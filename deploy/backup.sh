#!/usr/bin/env bash
# Copy the SQLite database and Chroma index out of the Docker volume (run on the Lightsail instance).
set -euo pipefail
STAMP=$(date +%Y%m%d-%H%M%S)
mkdir -p ~/backups
docker compose exec -T api tar czf - -C /app/var . > ~/backups/autodiagnose-$STAMP.tgz
echo "Saved ~/backups/autodiagnose-$STAMP.tgz"
