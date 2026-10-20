#!/bin/sh
# node_modules vive en un volumen de docker que no se actualiza solo al reconstruir la imagen.
# Si package-lock.json cambió desde la última instalación, se sincroniza antes de seguir.
set -e
if ! cmp -s package-lock.json node_modules/.sta-lock; then
  echo "package-lock.json cambió: instalando dependencias…"
  npm install --no-audit --no-fund
  cp package-lock.json node_modules/.sta-lock
fi
exec "$@"
