#!/usr/bin/env bash
# lib/ollama.sh — Ollama API wrapper with retry, timeout, token counting
# Source this file: source "$(dirname "$0")/lib/ollama.sh"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source "$SCRIPT_DIR/.env"
source "$SCRIPT_DIR/scripts/lib/retry.sh"

OLLAMA_API="${OLLAMA_HOST:-127.0.0.1:11434}"
OLLAMA_DEFAULT_MODEL="${OLLAMA_MODEL:-qwen3.5:9b-q4_K_M}"

# Call Ollama generate API with retry
# Usage: ollama_generate <prompt> [model] [max_tokens] [temperature]
ollama_generate() {
    local prompt="$1"
    local model="${2:-$OLLAMA_DEFAULT_MODEL}"
    local max_tokens="${3:-4096}"
    local temperature="${4:-0.2}"

    local response
    response=$(retry 3 2 curl -s --max-time 300 \
        "http://${OLLAMA_API}/api/generate" \
        -d "$(printf '%s' "$prompt" | "$SCIRES_VENV/bin/python3" -c "
import sys, json
prompt = sys.stdin.read()
print(json.dumps({
    'model': '$model',
    'prompt': prompt,
    'stream': False,
    'options': {
        'num_predict': $max_tokens,
        'temperature': $temperature
    }
}))
")")

    if [ $? -ne 0 ]; then
        echo '{"error": "Ollama request failed after retries"}' >&2
        return 1
    fi

    echo "$response"
}

# Call Ollama chat API for structured conversation
# Usage: ollama_chat <system_prompt> <user_message> [model] [max_tokens] [temperature]
ollama_chat() {
    local system_prompt="$1"
    local user_message="$2"
    local model="${3:-$OLLAMA_DEFAULT_MODEL}"
    local max_tokens="${4:-4096}"
    local temperature="${5:-0.2}"

    local response
    response=$(retry 3 2 curl -s --max-time 300 \
        "http://${OLLAMA_API}/api/chat" \
        -d "$("$SCIRES_VENV/bin/python3" -c "
import json
print(json.dumps({
    'model': '$model',
    'messages': [
        {'role': 'system', 'content': $(printf '%s' "$system_prompt" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')},
        {'role': 'user', 'content': $(printf '%s' "$user_message" | python3 -c 'import sys,json; print(json.dumps(sys.stdin.read()))')}
    ],
    'stream': False,
    'options': {
        'num_predict': $max_tokens,
        'temperature': $temperature
    }
}))
")")

    if [ $? -ne 0 ]; then
        echo '{"error": "Ollama chat request failed after retries"}' >&2
        return 1
    fi

    echo "$response"
}

# Extract just the response text from Ollama output
ollama_extract_response() {
    local json_response="$1"
    "$SCIRES_VENV/bin/python3" -c "
import json, sys
try:
    data = json.loads('''$json_response''')
    if 'response' in data:
        print(data['response'])
    elif 'message' in data and 'content' in data['message']:
        print(data['message']['content'])
    else:
        print(json.dumps(data))
except Exception as e:
    print(f'Parse error: {e}', file=sys.stderr)
    sys.exit(1)
"
}

# Get token count from Ollama response
ollama_token_count() {
    local json_response="$1"
    "$SCIRES_VENV/bin/python3" -c "
import json
data = json.loads('''$json_response''')
prompt_tokens = data.get('prompt_eval_count', 0)
completion_tokens = data.get('eval_count', 0)
print(prompt_tokens + completion_tokens)
"
}

# Check if Ollama is available
ollama_health() {
    curl -s --max-time 5 "http://${OLLAMA_API}/api/tags" > /dev/null 2>&1
}
