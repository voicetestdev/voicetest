#!/usr/bin/env bash
# Start the local LiveKit + STT/TTS stack (the same services live calls use,
# and that the live-call integration tests run against).
#
# Usable locally and in CI. Brings up the services defined in
# voicetest/compose/docker-compose.yml and waits until each is reachable:
#   - livekit  ws://localhost:7880  (LiveKit dev server)
#   - whisper  http://localhost:8001 (faster-whisper STT, OpenAI-compatible)
#   - kokoro   http://localhost:8002 (Kokoro TTS, OpenAI-compatible)
#
# Usage:
#   scripts/services.sh up      # start and wait (default)
#   scripts/services.sh down    # stop and remove
set -euo pipefail

COMPOSE_FILE="voicetest/compose/docker-compose.yml"
SERVICES=(livekit whisper kokoro)
ACTION="${1:-up}"

wait_for_port() {
  local name="$1" port="$2" timeout="${3:-180}" elapsed=0
  echo "waiting for ${name} on :${port} ..."
  while ! (exec 3<>"/dev/tcp/localhost/${port}") 2>/dev/null; do
    sleep 2
    elapsed=$((elapsed + 2))
    if [ "${elapsed}" -ge "${timeout}" ]; then
      echo "ERROR: ${name} not reachable on :${port} after ${timeout}s" >&2
      docker compose -f "${COMPOSE_FILE}" logs "${name}" >&2 || true
      return 1
    fi
  done
  echo "${name} is up on :${port}"
}

case "${ACTION}" in
  up)
    # Tolerate a pre-existing stack already bound to these ports (local dev):
    # readiness is confirmed by the port waits below, not by this command.
    docker compose -f "${COMPOSE_FILE}" up -d "${SERVICES[@]}" \
      || echo "compose up returned non-zero; verifying readiness of existing services..."
    wait_for_port livekit 7880
    wait_for_port whisper 8001
    wait_for_port kokoro 8002
    echo "all test services ready"
    ;;
  down)
    docker compose -f "${COMPOSE_FILE}" down -v
    ;;
  *)
    echo "usage: $0 [up|down]" >&2
    exit 1
    ;;
esac
