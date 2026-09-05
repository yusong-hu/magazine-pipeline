#!/bin/bash
# Run TTS for all 3 articles, with isolated state per article.
set -e

source /tmp/edge-tts-env/bin/activate

ARTICLES_DIR="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/articles"
AUDIO_BASE="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/audio"
mkdir -p "$AUDIO_BASE"

for f in "$ARTICLES_DIR"/*.md; do
    base=$(basename "$f" .md)
    out_dir="$AUDIO_BASE/$base"
    out="$out_dir/final.mp3"
    state="$out_dir/.tts-state.json"
    mkdir -p "$out_dir"

    if [ -f "$out" ] && [ -s "$out" ]; then
        echo "[skip] $base (output exists)"
        continue
    fi

    echo "=== [start] $base ==="
    # Pass --state-file so this article's state doesn't collide with others
    python /Users/yusonghu/.minimax/skills/text-to-speech/scripts/tts_generate.py \
        --input "$f" \
        --output "$out" \
        --voice en-GB-RyanNeural \
        --cooldown 3 \
        --max-chars 250 \
        --state-file "$state" \
        || { echo "[failed] $base"; continue; }
    echo "=== [done] $base ==="
done

echo "[all done]"
