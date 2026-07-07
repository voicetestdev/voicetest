#!/usr/bin/env bash
# Start the local LiveKit + STT/TTS stack (the same services live calls use,
# and that the live-call integration tests run against).
#
# Usable locally and in CI. Brings up the services defined in
# voicetest/compose/docker-compose.yml and waits until each is reachable:
#   - livekit  ws://localhost:7880  (LiveKit dev server)
#   - whisper  http://localhost:8001 (faster-whisper STT, OpenAI-compatible)
#   - kokoro   http://localhost:8002 (Kokoro TTS, OpenAI-compatible)
#   - ollama   http://localhost:11434 (local LLM for the agent's spoken turn)
#
# Usage:
#   scripts/services.sh up               # start and wait for all services (default)
#   scripts/services.sh up ollama        # start and wait for a subset only
#   scripts/services.sh down             # stop and remove
set -euo pipefail

COMPOSE_FILE="voicetest/compose/docker-compose.yml"
SERVICES=(livekit whisper kokoro ollama)
OLLAMA_MODEL="${OLLAMA_MODEL:-qwen2.5:0.5b}"
ACTION="${1:-up}"

port_for() {
  case "$1" in
    livekit) echo 7880 ;;
    whisper) echo 8001 ;;
    kokoro) echo 8002 ;;
    ollama) echo 11434 ;;
    *) echo "" ;;
  esac
}

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
    # Bring up all services by default, or only the ones named after 'up'.
    requested=("${@:2}")
    if [ "${#requested[@]}" -eq 0 ]; then
      requested=("${SERVICES[@]}")
    fi
    # Tolerate a pre-existing stack already bound to these ports (local dev):
    # readiness is confirmed by the port waits below, not by this command.
    docker compose -f "${COMPOSE_FILE}" up -d "${requested[@]}" \
      || echo "compose up returned non-zero; verifying readiness of existing services..."
    for svc in "${requested[@]}"; do
      wait_for_port "${svc}" "$(port_for "${svc}")"
      if [ "${svc}" = "ollama" ]; then
        # The mapped port is up before the ollama server is ready to serve, so
        # retry the pull until the server accepts it.
        echo "pulling ollama model ${OLLAMA_MODEL} ..."
        pulled=0
        for _ in $(seq 1 30); do
          if docker compose -f "${COMPOSE_FILE}" exec -T ollama ollama pull "${OLLAMA_MODEL}"; then
            pulled=1
            break
          fi
          echo "ollama server not ready yet, retrying pull ..."
          sleep 2
        done
        if [ "${pulled}" -ne 1 ]; then
          echo "ERROR: ollama pull failed after retries" >&2
          exit 1
        fi
      fi
    done
    echo "requested test services ready"
    ;;
  down)
    docker compose -f "${COMPOSE_FILE}" down -v
    ;;
  *)
    echo "usage: $0 [up|down] [service...]" >&2
    exit 1
    ;;
esac
