#!/bin/sh
set -eu

: "${CI_COMMIT_SHA:?CI_COMMIT_SHA is required}"
: "${DEPLOY_DIR:=/srv/docker/spielplatzkontrolle}"

COMPOSE_FILE="$DEPLOY_DIR/compose.autodeploy.yaml"
ENV_FILE="$DEPLOY_DIR/.env"
SERVICE=spielplatzkontrolle
NEW_IMAGE="playground-check-python:${CI_COMMIT_SHA}"

[ -f "$COMPOSE_FILE" ] || { echo "Missing host deployment compose: $COMPOSE_FILE" >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Missing host .env: $ENV_FILE" >&2; exit 1; }

docker network inspect nginx >/dev/null
docker network inspect postgis >/dev/null

# Do not echo credentials or the contents of the .env file.
previous_image="$(docker inspect --format '{{.Config.Image}}' "$SERVICE" 2>/dev/null || true)"
printf 'Previous image: %s\n' "${previous_image:-none}"
printf 'Building image for commit: %s\n' "$CI_COMMIT_SHA"
docker build --pull -t "$NEW_IMAGE" -f Dockerfile .

export PLAYGROUND_IMAGE="$NEW_IMAGE"
docker compose -p spielplatzkontrolle --project-directory "$DEPLOY_DIR" \
  --env-file "$ENV_FILE" -f "$COMPOSE_FILE" config --quiet

if docker compose -p spielplatzkontrolle --project-directory "$DEPLOY_DIR" \
    --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-build --wait --wait-timeout 180; then
  printf 'Deployment successful: %s\n' "$NEW_IMAGE"
  exit 0
fi

printf 'New container failed its readiness check; trying rollback to %s\n' "${previous_image:-unknown}" >&2
if [ -n "$previous_image" ] && docker image inspect "$previous_image" >/dev/null 2>&1; then
  export PLAYGROUND_IMAGE="$previous_image"
  if docker compose -p spielplatzkontrolle --project-directory "$DEPLOY_DIR" \
      --env-file "$ENV_FILE" -f "$COMPOSE_FILE" up -d --no-build --wait --wait-timeout 180; then
    printf 'Rollback completed: %s\n' "$previous_image" >&2
  else
    printf 'ERROR: Rollback also failed; inspect container logs immediately.\n' >&2
  fi
else
  printf 'ERROR: Previous image unavailable; cannot roll back automatically.\n' >&2
fi
exit 1
