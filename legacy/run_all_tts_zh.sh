#!/bin/bash
# Run TTS for all 3 articles in Chinese (zh-CN-YunyangNeural, news voice).
# Uses articles-zh/ as input and audio/<name>/zh/final.mp3 as output.
set -e

source /tmp/edge-tts-env/bin/activate

ARTICLES_DIR="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles-zh"
AUDIO_BASE="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/audio"
mkdir -p "$AUDIO_BASE"

for f in "$ARTICLES_DIR"/*.md; do
    base=$(basename "$f" .md)        # 01_zh, 02_zh, 03_zh
    # Output naming: same as English, but in a "zh" subdir to avoid conflict
    # base_zh is already like 02_zh, we want audio/02_zh/final.mp3
    out_dir="$AUDIO_BASE/$base"
    out="$out_dir/final.mp3"
    state="$out_dir/.tts-state.json"
    mkdir -p "$out_dir"

    if [ -f "$out" ] && [ -s "$out" ]; then
        echo "[skip] $base (output exists)"
        continue
    fi

    echo "=== [start] $base ==="
    python /Users/yusonghu/.minimax/skills/text-to-speech/scripts/tts_generate.py \
        --input "$f" \
        --output "$out" \
        --voice zh-CN-YunyangNeural \
        --cooldown 3 \
        --max-chars 250 \
        --state-file "$state" \
        || { echo "[failed] $base"; continue; }
    echo "=== [done] $base ==="
done

echo "[all zh done]"
