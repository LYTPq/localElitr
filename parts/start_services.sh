#!/usr/bin/env bash
set -euo pipefail

pids=()

cleanup() {
  for pid in "${pids[@]:-}"; do 
    kill "$pid" >/dev/null 2>&1 || true
  done
  wait || true
}
trap cleanup EXIT INT TERM


"$PY" -u "$CT2_SERVER" \
  --host 127.0.0.1 --port "$CT2_PORT" \
  --ct2_model "$CT2_MODEL_DIR" \
  --hf_tokenizer "$HF_TOKENIZER" \
  --inter_threads "$CT2_INTER_THREADS" \
  --intra_threads "$CT2_INTRA_THREADS" \
  --device "$CT2_DEVICE" \
  --beam "$CT2_BEAM" &
pids+=($!)


vac_flags=()
if [[ "${WH_VAC:-0}" == "1" ]]; then
  vac_flags+=(--vac --vac-chunk-size "$WH_VAC_CHUNK_SIZE")
fi


"$PY" -u "/app/SimulStreaming/simulstreaming_whisper_server.py" \
  --host 127.0.0.1 --port "$ASR_PORT" \
  --lan "$WH_LANGUAGE" --task "$WH_TASK" \
  --model_path "$WHISPER_MODEL" \
  --beams "$WH_BEAMS" --frame_threshold "$WH_FRAME_THRESHOLD" \
  "${vac_flags[@]}" \
  --min-chunk-size "$WH_MIN_CHUNK_SIZE" \
  --audio_min_len "$WH_AUDIO_MIN_LEN" --audio_max_len "$WH_AUDIO_MAX_LEN" \
  --init_prompt "$WH_INIT_PROMPT" \
  --log-level "$WH_LOG_LEVEL" &
pids+=($!)


echo "[Services] Starting TextFlow on $TEXTFLOW_PORT..."
online-text-flow server --host 0.0.0.0 --port "$TEXTFLOW_PORT" &
pids+=($!)

tail -f /dev/null