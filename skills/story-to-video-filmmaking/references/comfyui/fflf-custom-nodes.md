# Custom Node Prerequisites for FFLF Seed Hunter

The LTX 2.3 FFLF Seed Hunter workflow depends on several custom ComfyUI node suites to handle multi-stage sampling, resolution calculations, image resizing, and video stitching.

Ensure the following custom nodes are installed on your ComfyUI instance before queuing tasks.

---

## Required Node Suites

### 1. ComfyUI-KJNodes
* **Repository**: [kijai/ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)
* **Description**: General utility nodes for math calculation and image resizing.
* **Nodes Used**:
  - `SimpleCalculatorKJ` (resolves temporal dimensions, steps, and crop boundaries)
  - `ImageResizeKJv2` (resizes keyframes to match generation canvas aspect ratios)
  - `VAELoaderKJ` (loads the video VAE model)
  - `PrimitiveInt` (passes integer parameters like seeds)
  - `PathchSageAttentionKJ` (optimizes attention computation speed)

### 2. ComfyUI-LTXVideo
* **Repository**: [kijai/ComfyUI-LTXVideo](https://github.com/kijai/ComfyUI-LTXVideo)
* **Description**: Core nodes for loading, conditioning, sampling, and upscaling LTX 2.3 video model inputs.
* **Nodes Used**:
  - `EmptyLTXVLatentVideo` (generates the initial empty video latent tensor)
  - `LTXVPreprocess` (processes keyframe stills into conditioning latents)
  - `LTXVAddGuide` (injects first/last frame guides)
  - `LTXVCropGuides` (matches guide frame boundaries)
  - `LTXVConditioning` (applies prompt and negative guidance to video latents)
  - `LTX2_NAG` (Non-Adversarial Guidance adjustments)
  - `LTXVConcatAVLatent` & `LTXVSeparateAVLatent` (manages latent audio-video tensor concatenation)
  - `LTXVEmptyLatentAudio` (creates silent audio tracks to prevent VAE decoder crashes)
  - `LTX2SamplingPreviewOverride` (overrides standard sampler previews for video feedback)
  - `LTXVLatentUpsampler` (upscales latents by 2x between sampling stages)

### 3. ComfyUI-Impact-Pack
* **Repository**: [ltdrdata/ComfyUI-Impact-Pack](https://github.com/ltdrdata/ComfyUI-Impact-Pack)
* **Description**: Advanced flow-control nodes.
* **Nodes Used**:
  - `ImpactSwitch` (routes the selected Stage 1 preview latent to the Stage 2 upscaler based on the user or evaluator index)

### 4. ComfyUI-VideoHelperSuite (VHS)
* **Repository**: [Kosinkadink/ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)
* **Description**: Core suite for reading and combining video/audio streams.
* **Nodes Used**:
  - `VHS_VideoCombine` (combines VAE-decoded frame tensors into final `.mp4` video files)

---

## Installation via CLI

If you are setting up a new VPS worker, run these commands in your `ComfyUI/custom_nodes/` directory:

```bash
cd custom_nodes
git clone https://github.com/kijai/ComfyUI-KJNodes.git
git clone https://github.com/kijai/ComfyUI-LTXVideo.git
git clone https://github.com/ltdrdata/ComfyUI-Impact-Pack.git
git clone https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite.git
```

Restart ComfyUI after cloning the nodes.
