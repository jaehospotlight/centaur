#!/bin/bash
# nano-banana — generate or edit images in the active Slack thread
set -euo pipefail

usage() {
  cat <<'EOF' >&2
Usage:
  nano-banana generate "<prompt>" [options]
  nano-banana edit <image_path> "<prompt>" [options]

Options:
  --model <flash|pro|model-id>
  --aspect-ratio <1:1|3:4|4:3|9:16|16:9>
  --size <1K|2K|4K>
  --person-generation <DONT_ALLOW|ALLOW_ADULT|ALLOW_ALL>
  --search
  --thinking-budget <int>
  --thinking-level <minimal|low|medium|high>
  --output <path>
  --comment "<slack message>"   Save locally and upload to the current Slack thread
EOF
  exit 1
}

if [ $# -lt 2 ]; then
  usage
fi

cmd="$1"
shift

U="${AI_V2_API_URL:-http://api:8000}"
_KEY="${AI_V2_API_KEY:-}"
if [ -f /home/agent/.api_key ]; then
  _KEY="$(cat /home/agent/.api_key)"
fi
AUTH_ARGS=()
if [ -n "${_KEY}" ]; then
  AUTH_ARGS=(-H "Authorization: Bearer ${_KEY}")
fi

model="flash"
aspect_ratio=""
image_size=""
person_generation=""
use_google_search="false"
thinking_budget=""
thinking_level=""
output_path=""
comment=""

api_post() {
  local method="$1"
  local body="$2"
  local response
  local curl_args=(
    -sS
    -H "Content-Type: application/json"
    -d "$body"
    --write-out $'\n__HTTP_STATUS__:%{http_code}'
    "$U/tools/nano-banana/$method"
  )

  if [ ${#AUTH_ARGS[@]} -gt 0 ]; then
    curl_args=("${AUTH_ARGS[@]}" "${curl_args[@]}")
  fi

  response="$(curl "${curl_args[@]}")"

  local status="${response##*__HTTP_STATUS__:}"
  local payload="${response%$'\n'__HTTP_STATUS__:*}"

  if [[ ! "$status" =~ ^2 ]]; then
    echo "Nano Banana API request failed with HTTP $status" >&2
    echo "$payload" >&2
    exit 1
  fi

  printf '%s' "$payload"
}

decode_result() {
  local envelope="$1"
  local result_json
  result_json="$(printf '%s' "$envelope" | jq -er '.result | fromjson')"

  local error_text
  error_text="$(printf '%s' "$result_json" | jq -r '.error // empty')"
  if [ -n "$error_text" ]; then
    echo "$error_text" >&2
    exit 1
  fi

  printf '%s' "$result_json"
}

write_output_file() {
  local result_json="$1"
  local requested_output="$2"
  local filename
  local base64_data
  local resolved_output

  filename="$(printf '%s' "$result_json" | jq -r '.filename // empty')"
  base64_data="$(printf '%s' "$result_json" | jq -er '.content_base64')"

  if [ -n "$requested_output" ]; then
    resolved_output="$requested_output"
  else
    resolved_output="/tmp/${filename:-nano-banana-$(date +%s).png}"
  fi

  mkdir -p "$(dirname "$resolved_output")"
  printf '%s' "$base64_data" | base64 -d > "$resolved_output"
  printf '%s' "$resolved_output"
}

parse_common_flags() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --model)
        [ $# -ge 2 ] || usage
        model="$2"
        shift 2
        ;;
      --aspect-ratio)
        [ $# -ge 2 ] || usage
        aspect_ratio="$2"
        shift 2
        ;;
      --size)
        [ $# -ge 2 ] || usage
        image_size="$2"
        shift 2
        ;;
      --person-generation)
        [ $# -ge 2 ] || usage
        person_generation="$2"
        shift 2
        ;;
      --search)
        use_google_search="true"
        shift
        ;;
      --thinking-budget)
        [ $# -ge 2 ] || usage
        thinking_budget="$2"
        shift 2
        ;;
      --thinking-level)
        [ $# -ge 2 ] || usage
        thinking_level="$2"
        shift 2
        ;;
      --output)
        [ $# -ge 2 ] || usage
        output_path="$2"
        shift 2
        ;;
      --comment)
        [ $# -ge 2 ] || usage
        comment="$2"
        shift 2
        ;;
      *)
        echo "Unknown option: $1" >&2
        usage
        ;;
    esac
  done
}

run_generate() {
  prompt="$1"
  shift
  parse_common_flags "$@"
  default_filename="nano-banana-$(date +%s).png"

  body="$(jq -nc \
    --arg prompt "$prompt" \
    --arg model "$model" \
    --arg aspect_ratio "$aspect_ratio" \
    --arg image_size "$image_size" \
    --arg person_generation "$person_generation" \
    --arg thinking_budget "$thinking_budget" \
    --arg thinking_level "$thinking_level" \
    --argjson use_google_search "$use_google_search" \
    --arg filename "$(basename "${output_path:-$default_filename}")" \
    '{
      prompt: $prompt,
      model: $model,
      use_google_search: $use_google_search,
      filename: $filename
    }
    + (if $aspect_ratio != "" then {aspect_ratio: $aspect_ratio} else {} end)
    + (if $image_size != "" then {image_size: $image_size} else {} end)
    + (if $person_generation != "" then {person_generation: $person_generation} else {} end)
    + (if $thinking_level != "" then {thinking_level: $thinking_level} else {} end)
    + (if $thinking_budget != "" then {thinking_budget: ($thinking_budget | tonumber)} else {} end)')"

  result_json="$(decode_result "$(api_post generate "$body")")"
  file_path="$(write_output_file "$result_json" "$output_path")"
}

run_edit() {
  [ $# -ge 2 ] || usage
  image_path="$1"
  prompt="$2"
  shift 2
  parse_common_flags "$@"

  if [ ! -f "$image_path" ]; then
    echo "Input image not found: $image_path" >&2
    exit 1
  fi

  input_name="$(basename "$image_path")"
  input_stem="${input_name%.*}"
  input_ext=""
  if [ "$input_stem" != "$input_name" ]; then
    input_ext=".${input_name##*.}"
  else
    input_stem="$input_name"
  fi
  default_filename="${input_stem}_edited${input_ext}"

  mime_type="$(python3 - "$image_path" <<'PY'
import mimetypes
import sys
print(mimetypes.guess_type(sys.argv[1])[0] or "image/png")
PY
)"
  image_base64="$(base64 < "$image_path" | tr -d '\n')"

  body="$(jq -nc \
    --arg prompt "$prompt" \
    --arg image_base64 "$image_base64" \
    --arg image_mime_type "$mime_type" \
    --arg model "$model" \
    --arg aspect_ratio "$aspect_ratio" \
    --arg image_size "$image_size" \
    --arg person_generation "$person_generation" \
    --arg thinking_budget "$thinking_budget" \
    --arg thinking_level "$thinking_level" \
    --argjson use_google_search "$use_google_search" \
    --arg filename "$(basename "${output_path:-$default_filename}")" \
    '{
      prompt: $prompt,
      image_base64: $image_base64,
      image_mime_type: $image_mime_type,
      model: $model,
      use_google_search: $use_google_search,
      filename: $filename
    }
    + (if $aspect_ratio != "" then {aspect_ratio: $aspect_ratio} else {} end)
    + (if $image_size != "" then {image_size: $image_size} else {} end)
    + (if $person_generation != "" then {person_generation: $person_generation} else {} end)
    + (if $thinking_level != "" then {thinking_level: $thinking_level} else {} end)
    + (if $thinking_budget != "" then {thinking_budget: ($thinking_budget | tonumber)} else {} end)')"

  result_json="$(decode_result "$(api_post edit "$body")")"
  file_path="$(write_output_file "$result_json" "$output_path")"
}

case "$cmd" in
  generate)
    run_generate "$@"
    ;;
  edit)
    run_edit "$@"
    ;;
  *)
    usage
    ;;
esac

if [ -n "$comment" ]; then
  slack-upload "$file_path" "$comment"
else
  printf '%s\n' "$file_path"
fi
