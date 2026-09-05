#!/bin/bash
# TTS all 20 articles x 3 audios = 60 audio files.
# Each article's 3 audios are generated in parallel.
# Articles are processed in sequence (not parallel across articles) to avoid
# hammering edge-tts with too many concurrent requests.
set -e

source /tmp/edge-tts-env/bin/activate

TTS_INPUTS_DIR="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/tts_inputs"
AUDIO_BASE="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/audio"
TTS_LOG="/Users/yusonghu/Documents/个人电脑控制/new-yorker-import/tts-all-in-one.log"

mkdir -p "$AUDIO_BASE"
> "$TTS_LOG"

# Process each article
for d in "$TTS_INPUTS_DIR"/*_tts; do
    num=$(basename "$d" | sed 's/_tts$//')
    out_dir="$AUDIO_BASE/$num"
    mkdir -p "$out_dir"

    en_input="$d/01_en.md"
    zh_tr_input="$d/02_zh_tr.md"
    zh_an_input="$d/03_zh_an.md"

    # 1. English full text
    if [ -f "$en_input" ] && [ ! -f "$out_dir/en.mp3" ]; then
        echo "=== [$num] EN ===" | tee -a "$TTS_LOG"
        python /Users/yusonghu/.minimax/skills/text-to-speech/scripts/tts_generate.py \
            --input "$en_input" \
            --output "$out_dir/en.mp3" \
            --voice en-GB-RyanNeural \
            --cooldown 3 \
            --max-chars 250 \
            --state-file "$out_dir/.en-state.json" \
            >> "$TTS_LOG" 2>&1 || echo "  EN failed" | tee -a "$TTS_LOG"
    fi

    # 2. Chinese translation
    if [ -f "$zh_tr_input" ] && [ -s "$zh_tr_input" ] && [ ! -f "$out_dir/zh_tr.mp3" ]; then
        echo "=== [$num] ZH-tr ===" | tee -a "$TTS_LOG"
        python /Users/yusonghu/.minimax/skills/text-to-speech/scripts/tts_generate.py \
            --input "$zh_tr_input" \
            --output "$out_dir/zh_tr.mp3" \
            --voice zh-CN-YunyangNeural \
            --cooldown 3 \
            --max-chars 250 \
            --state-file "$out_dir/.zh-tr-state.json" \
            >> "$TTS_LOG" 2>&1 || echo "  ZH-tr failed" | tee -a "$TTS_LOG"
    fi

    # 3. Chinese analysis
    if [ -f "$zh_an_input" ] && [ -s "$zh_an_input" ] && [ ! -f "$out_dir/zh_an.mp3" ]; then
        echo "=== [$num] ZH-an ===" | tee -a "$TTS_LOG"
        python /Users/yusonghu/.minimax/skills/text-to-speech/scripts/tts_generate.py \
            --input "$zh_an_input" \
            --output "$out_dir/zh_an.mp3" \
            --voice zh-CN-YunyangNeural \
            --cooldown 3 \
            --max-chars 250 \
            --state-file "$out_dir/.zh-an-state.json" \
            >> "$TTS_LOG" 2>&1 || echo "  ZH-an failed" | tee -a "$TTS_LOG"
    fi

    echo "--- [$num] done ---" | tee -a "$TTS_LOG"
done

echo ""
echo "==================================="
echo "ALL TTS COMPLETE"
echo "==================================="
ls -la "$AUDIO_BASE"/*/en.mp3 2>/dev/null | wc -l
ls -la "$AUDIO_BASE"/*/zh_tr.mp3 2>/dev/null | wc -l
ls -la "$AUDIO_BASE"/*/zh_an.mp3 2>/dev/null | wc -l
