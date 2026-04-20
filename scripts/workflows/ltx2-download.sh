#!/bin/bash
# ---
# name: LTX 2.3
# aliases: [ltx, ltx 2.3, ltx2.3, ltx-2.3]
# description: Downloads all models required for LTX 2.3 and applies requisite patch.
# size: ~60GB
# min_vram: 24GB
# ---
set -e

BASE_DIR="/workspace/ComfyUI/models"

echo "==> Creating directories..."
mkdir -p "$BASE_DIR"/{loras/ltx2,unet,text_encoders,vae,latent_upscale_models,checkpoints}

echo "==> Checking aria2..."
if ! command -v aria2c &> /dev/null; then
    echo "aria2 not found, installing..."
    sudo apt update && sudo apt install -y aria2
else
    echo "aria2 already installed"
fi

echo "==> Setting up ComfyUI nodes..."
cd /workspace/ComfyUI
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi
if command -v comfy &> /dev/null; then
    comfy node install https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI
else
    echo "comfy-cli not found, cloning node repository manually..."
    cd custom_nodes
    git clone https://github.com/WhatDreamsCost/WhatDreamsCost-ComfyUI || true
    cd ..
fi

echo "==> Starting downloads..."

aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/unet" -o "ltx-2.3-22b-dev-nvfp4.safetensors" "https://huggingface.co/Lightricks/LTX-2.3-nvfp4/resolve/main/ltx-2.3-22b-dev-nvfp4.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/unet" -o "ltx-2.3-22b-dev-fp8.safetensors" "https://huggingface.co/Lightricks/LTX-2.3-fp8/resolve/main/ltx-2.3-22b-dev-fp8.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/text_encoders" -o "gemma_3_12B_it_fp4_mixed.safetensors" "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/text_encoders/gemma_3_12B_it_fp4_mixed.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/loras" -o "ltx-2.3-22b-distilled-lora-384.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-22b-distilled-lora-384.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/loras" -o "gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" "https://huggingface.co/Comfy-Org/ltx-2/resolve/main/split_files/loras/gemma-3-12b-it-abliterated_lora_rank64_bf16.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "LTX23_video_vae_bf16.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_video_vae_bf16.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "LTX23_audio_vae_bf16.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/LTX23_audio_vae_bf16.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/latent_upscale_models" -o "ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x1.5-1.0.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/latent_upscale_models" -o "ltx-2.3-spatial-upscaler-x2-1.1.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-spatial-upscaler-x2-1.1.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/latent_upscale_models" -o "ltx-2.3-temporal-upscaler-x2-1.0.safetensors" "https://huggingface.co/Lightricks/LTX-2.3/resolve/main/ltx-2.3-temporal-upscaler-x2-1.0.safetensors" &
aria2c -x 16 -s 16 -k 1M -d "$BASE_DIR/vae" -o "taeltx2_3.safetensors" "https://huggingface.co/Kijai/LTX2.3_comfy/resolve/main/vae/taeltx2_3.safetensors" &

wait
echo "==> All downloads completed!"

echo "==> Creating symlinks and copies..."
ln -sf ../unet/ltx-2.3-22b-dev-fp8.safetensors "$BASE_DIR/checkpoints/ltx-2.3-22b-dev-fp8.safetensors"
ln -sf ../unet/ltx-2.3-22b-dev-nvfp4.safetensors "$BASE_DIR/checkpoints/ltx-2.3-22b-dev-nvfp4.safetensors"
cp "$BASE_DIR/loras/ltx-2.3-22b-distilled-lora-384.safetensors" "$BASE_DIR/loras/ltx2/ltx-2.3-22b-distilled-lora-dynamic_fro09_avg_rank_105_bf16.safetensors"

echo "==> Applying patch..."
PATCH_FILE="/workspace/ComfyUI/comfy/ldm/lightricks/symmetric_patchifier.py"
if [ -f "$PATCH_FILE" ]; then
    if ! grep -q "audio_latents.dim()" "$PATCH_FILE"; then
      sed -i "/b, _, t, _ = audio_latents.shape/i\        if audio_latents.dim() == 5:\n            audio_latents = audio_latents.squeeze(1)" "$PATCH_FILE"
    fi
else
    echo "Patch file not found, skipping patch."
fi

echo "==> Done!"
echo "👉 Restart ComfyUI or click Refresh in the UI."
