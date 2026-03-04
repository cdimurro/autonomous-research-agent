#!/usr/bin/env bash
# lib/retry.sh — Generic retry with exponential backoff
# Usage: retry <max_retries> <base_delay_s> <command...>
# Example: retry 3 2 curl -s http://example.com

retry() {
    local max_retries="${1:?Usage: retry <max_retries> <base_delay_s> <command...>}"
    local base_delay="${2:?}"
    shift 2
    local attempt=0
    local exit_code=0

    while [ "$attempt" -lt "$max_retries" ]; do
        attempt=$((attempt + 1))
        if "$@"; then
            return 0
        fi
        exit_code=$?
        if [ "$attempt" -lt "$max_retries" ]; then
            local delay=$((base_delay * (2 ** (attempt - 1))))
            echo "[retry] Attempt $attempt/$max_retries failed (exit $exit_code). Retrying in ${delay}s..." >&2
            sleep "$delay"
        fi
    done

    echo "[retry] All $max_retries attempts failed (last exit $exit_code)" >&2
    return "$exit_code"
}
