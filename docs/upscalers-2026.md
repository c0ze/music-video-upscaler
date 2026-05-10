# Upscaler research for low-resolution music videos (2026)

Scope: 240p–1080p music videos sourced primarily from YouTube, target output 2K
or 4K MKV with lossless audio.

Hardware in scope:

- **Apple M4 Mac mini** (Apple Silicon, unified memory, Metal/MPS, ANE)
- **CachyOS / Linux + AMD Radeon RX 9060 XT 16 GB** (RDNA4, 32 CUs, 64 AI
  accelerators, Vulkan + ROCm 6.4.1)

The current pipeline runs `realesrgan-ncnn-vulkan` because it is portable, GPU
agnostic via Vulkan, and ships pre-built binaries. That choice is still
defensible for both target machines, but several alternatives now produce
better results on heavy YouTube compression artefacts.

---

## TL;DR — what to actually use

The pipeline default is now **`realesr-general-x4v3`** (committed to `models/`,
auto-selected by every entry script). Switch model name when noise level
demands it; there is no `-dn` knob on the ncnn binary (Python-only — see note
at the bottom of the next section).

| Source quality | Best output / least friction | Best output / willing to invest |
|----------------|------------------------------|---------------------------------|
| 240p–360p, heavy block artefacts | `realesr-general-wdn-x4v3` (stronger denoise twin) | **FlashVSR** or **SeedVR2** in ComfyUI |
| 480p typical YouTube rip | `realesr-general-x4v3` *(default)* | **RealBasicVSR** or **SeedVR2** |
| 720p / 1080p clean | `realesr-general-x4v3` *(default)* — or `realesrgan-x4plus` at 2× when source is genuinely clean | **VideoGigaGAN-style** or **SeedVR2** at 2× |
| Anime / animated music videos | `realesr-animevideov3` (bundled, native 2/3/4×) | **APISR** (anime-specific) or **Real-CUGAN** |

Why these picks for *your* machines:

- **M4 Mac mini**: prefer **Vulkan-via-MoltenVK** binaries (Real-ESRGAN /
  Real-CUGAN / waifu2x ncnn) for the daily flow — they hit the GPU directly
  and avoid PyTorch/MPS quirks. Use **CoreML/ANE** ports (PiperSR, CoreML
  Real-ESRGAN, *Unsqueeze*) for fastest throughput when quality is OK.
  Only step up to **SeedVR2 ComfyUI on MPS** when a clip really needs it
  (currently has known MPS bugs, requires `PYTORCH_ENABLE_MPS_FALLBACK=1`).
- **AMD RX 9060 XT (RDNA4)**: stay on **Vulkan ncnn** binaries — they are the
  most stable path on this card today. ROCm 6.4.1 supports gfx1200 but
  several inference workloads still hang; the Vulkan backend is the safer
  default. Move to ROCm only for ComfyUI/PyTorch-only models.

---

## Why we moved off `realesrgan-x4plus` as the default

`realesrgan-x4plus` is a *general* GAN trained on real-world photographic
degradations. It tends to over-sharpen YouTube compression artefacts and can
introduce halos around high-contrast edges (concert lighting, drum kits,
white spotlights against black stage). Now the pipeline defaults instead to:

- **`realesr-general-x4v3`** *(default, ~2.4 MB)*: SRVGGNetCompact trained for
  real-world degradations. Smaller and faster than `x4plus`, and clearly
  cleaner on noisy YouTube re-encodes. Single biggest free quality win.
- **`realesr-general-wdn-x4v3`** *(included)*: same architecture, weights
  trained for stronger denoising. Use when v3 still leaves visible blocking.
- **`realesr-animevideov3`** *(included)*: correct choice for anime /
  animated lyric videos; native 2/3/4× variants.

All three live in `models/` and are auto-loaded by `-n <name>` — no extra
download, no flag plumbing.

> **`-dn` is Python-only.** The standalone `realesrgan-ncnn-vulkan` binary's
> CLI is `i:o:s:t:m:n:g:j:f:vxh` — no `-dn` option. xinntao's PyTorch
> `inference_realesrgan.py` interpolates between `x4v3` and `wdn-x4v3` at
> runtime via `-dn`; the ncnn binary cannot. To pick the equivalent on ncnn
> just switch the model name. If you really need a continuous denoise dial,
> run the Python pipeline directly.

---

## Alternatives that share the existing `ncnn-vulkan` workflow

These run on **the exact same Vulkan stack** (works on AMD, Intel, NVIDIA,
Apple Silicon via MoltenVK) and accept very similar CLI flags. They are
ideal first upgrades because we can plug them in via `REALESRGAN_BIN` (or
the Windows `windows/` folder) without rewriting the pipeline.

| Tool | Strengths | Weaknesses | Notes |
|------|-----------|------------|-------|
| **`realesrgan-ncnn-vulkan`** *(current)* | Best general support | Sometimes too sharp on noisy video | `-n {model}` selects model from `models/` |
| **`realcugan-ncnn-vulkan`** | Clean linework, 2/3/4×, 4 noise levels (`-n -1..3`), `-c` syncgap option to reduce video flicker | Best on 2D/anime; on live action it can plasticize skin | Drop-in CLI; `-n` is **noise level**, not model name |
| **`waifu2x-ncnn-vulkan`** | Mature, scales 1/2/4/8/16/32, very predictable | Older architecture; soft on textured live action | Same CLI shape as Real-ESRGAN ncnn |
| **Upscayl + `upscayl-ncnn`** | GUI on top of Real-ESRGAN-ncnn for one-off batches | Less suitable for scripted pipelines | Useful for visual A/B, not for the FLAC mux pipeline |

For each, install the binary and either symlink it into `tools/` or set
`REALESRGAN_BIN=/path/to/binary` before running `03_upscale.sh` /
`upscale_video.sh`. Models for waifu2x / Real-CUGAN come from the upstream
releases and live in their own model folders — you can place them under
`models/<engine>/` and pass `-m` via a small wrapper.

> Important: The shared `-n` flag changes meaning. Real-ESRGAN ncnn uses
> `-n MODEL_NAME`. waifu2x and Real-CUGAN ncnn use `-n NOISE_LEVEL`
> (`-1`/`0`/`1`/`2`/`3`). Don't reuse the same shell argument verbatim.

---

## Higher-quality, heavier alternatives (PyTorch / ComfyUI)

These are not drop-in replacements — they need a Python environment, and on
your AMD card they need ROCm (or Vulkan-Compute) builds of PyTorch. They
deliver materially better results on heavily compressed sources and on
720p→4K jumps, at significantly higher VRAM and runtime cost.

### Video-aware models (recommended for music videos)

| Model | Year / venue | Why it matters for this flow | Apple Silicon (M4) | AMD RX 9060 XT (Linux) |
|-------|-------------|------------------------------|--------------------|------------------------|
| **RealBasicVSR** | CVPR 2022 | Specifically built for real-world video SR with a pre-cleaning module that removes YouTube-style compression noise *before* propagation. Outperforms Real-ESRGAN on real-world video benchmarks. | Yes via PyTorch MPS (slow) | Yes via ROCm PyTorch (preferred) |
| **VideoGigaGAN** *(CVPR 2025)* | CVPR 2025 | GAN-based video SR up to 8× with strong high-frequency detail and temporal consistency. | Limited; weights require CUDA-style ops. | Best on ROCm PyTorch. |
| **SeedVR / SeedVR2** *(CVPR 2025 / ICLR 2026)* | Diffusion-transformer; SeedVR2 is one-step, ~4× faster than prior diffusion VSR. **ComfyUI node available.** | Works on MPS but with known issues (`aten::_upsample_bicubic2d_aa.out` not implemented; needs `PYTORCH_ENABLE_MPS_FALLBACK=1`). | Best path: ComfyUI + ROCm PyTorch. The 9060 XT is officially supported by ROCm 6.4.1; for stability, keep batch and tile sizes modest until you've validated. |
| **FlashVSR** | 2025/2026 | Diffusion video upscaler that runs in ComfyUI; community comparisons rate it above Topaz Video AI for realism, faster than SeedVR2. Low-VRAM preset works on 6 GB+ cards. | Same MPS caveats as SeedVR2. | Strong fit on the 9060 XT once you have a ROCm ComfyUI. |
| **APISR** (Anime Production-Inspired SR) | 2024 | Anime-specific; trained on production sources rather than DVD rips. Cleaner lines than `realesr-animevideov3` on modern animation. | PyTorch (MPS works for inference). | ROCm PyTorch. |

### Notes on practicality

- All ComfyUI-based models (SeedVR2, FlashVSR, SUPIR) trade a one-time install
  cost (45–120 min) for far better quality on heavily degraded YouTube rips.
- 240p–480p sources benefit the most from diffusion upscalers because the
  generative model fills in plausible high-frequency detail rather than
  amplifying compression noise.
- 720p–1080p clean sources often look best with a **2× pass** of a temporal
  model (RealBasicVSR / SeedVR2) rather than 4× of a frame-only model.

---

## Apple Silicon-specific options

The M4 Mac mini has CPU + GPU + Apple Neural Engine. Three useful tiers:

1. **Daily driver — Vulkan ncnn via MoltenVK**
   - Real-ESRGAN ncnn-vulkan, Real-CUGAN ncnn-vulkan, waifu2x-ncnn-vulkan all
     work today. This is what the current pipeline uses.
   - Pros: zero Python setup, predictable, batch-friendly, fits the existing
     POSIX scripts.
   - Cons: doesn't tap the ANE; M4 GPU is excellent so it's usually fast
     enough.

2. **Native CoreML / ANE**
   - **PiperSR**: tiny model (~928 KB) targeting Apple Neural Engine. Reports
     2× upscaling at ~48 FPS on M2 Max with 37.54 dB PSNR. Excellent for
     fast 1080p → 2160p batches when absolute peak quality isn't required.
   - **CoreML-converted Real-ESRGAN** (Ron Regev's guide): converts the
     existing weights to `.mlmodel` and runs them on the ANE/GPU.
   - **Unsqueeze** (commercial app): Metal-based offline upscaler up to 8K.
   - **myUpscaler** (open SwiftUI app): bundles CoreML Real-ESRGAN with a
     video pipeline (denoise / deblock / sharpen / interpolate).

3. **PyTorch MPS**
   - SeedVR2 / FlashVSR / RealBasicVSR all run via `torch.mps`. Memory
     management quirks remain in late 2025 / early 2026 (`MPS backend out of
     memory`, missing ops). Always set `PYTORCH_ENABLE_MPS_FALLBACK=1` and
     prefer smaller tiles.

---

## AMD RX 9060 XT (RDNA4, 16 GB, gfx1200) on Linux

- **Vulkan ncnn binaries are the most stable path** today. Mesa 25.1+ and
  Linux 6.14+ are the floor; CachyOS users typically already exceed both.
- ROCm 6.4.1 *officially* supports the 9060 XT for compute workloads, but
  several PyTorch / GGML stacks have intermittent OOM and hang issues on
  this card. Vulkan handles the same workloads gracefully, so:
  - For the deterministic frame pipeline, **stay on ncnn-vulkan**.
  - For ComfyUI experiments (SeedVR2 / FlashVSR), install **ROCm PyTorch**
    rather than Vulkan-Compute PyTorch — the latter still has spotty op
    coverage. Use `HSA_OVERRIDE_GFX_VERSION=12.0.0` if your ROCm build
    doesn't auto-detect gfx1200.
- AMD's **VPE 2.0** (merged into Mesa 26.2) is a hardware video processing
  engine — useful for *post-upscale* HDR/colorspace conversion and tone
  mapping, not for AI upscaling itself. Worth keeping an eye on.
- 16 GB VRAM is enough headroom to run SeedVR2 / FlashVSR at moderate tile
  sizes; 1080p → 2160p is comfortable, 1080p → 4320p is not.

---

## How this maps onto the existing repo

The biggest free win — switching the default model — is already done.
`realesr-general-x4v3` is the baked-in default for `03_upscale.sh`,
`upscale_video.sh`, `run_pipeline.sh`, and the matching `windows/*.ps1`.

To go further you don't need to change the pipeline architecture, just swap a
model name or a binary:

1. **Stronger denoise on very noisy sources.** Override the default model:
   ```bash
   MODEL=realesr-general-wdn-x4v3 ./run_pipeline.sh ./artist
   # or, manual stage:
   ./03_upscale.sh ./artist/tmp_frames ./artist/tmp_upscaled_4x 4 realesr-general-wdn-x4v3
   ```
   PowerShell:
   ```powershell
   .\windows\run_pipeline.ps1 -TargetFolder .\artist -Model realesr-general-wdn-x4v3
   ```

2. **Swap the binary** for `realcugan-ncnn-vulkan` or `waifu2x-ncnn-vulkan`
   when the source is animated:
   ```bash
   REALESRGAN_BIN=/usr/local/bin/realcugan-ncnn-vulkan \
     ./03_upscale.sh ./artist/tmp_frames ./artist/tmp_upscaled_4x 4 models-se
   ```
   *(For Real-CUGAN/waifu2x the 4th argument is the model directory. If we
   commit to supporting these officially we should add a thin wrapper that
   maps our `MODEL` argument to `-m` and `-n NOISE` correctly.)*

3. **Promote a separate ComfyUI workflow** for hero clips. Document it under
   `docs/comfyui-flashvsr.md` (future) so the deterministic pipeline stays
   simple while we keep an escape hatch for "this clip needs the diffusion
   treatment."

---

## Possible follow-ups

1. Add a `tools/install-realcugan.sh` companion next to `install-dependencies.sh`
   for the AMD/Linux box (it's a separate ncnn binary).
2. (Optional, later) Stand up a minimal ComfyUI launcher script under
   `extras/comfyui/` that points at SeedVR2 + FlashVSR custom nodes, with
   ROCm and MPS environment toggles. Use it only when a specific clip
   warrants the cost.
3. If continuous `-dn` interpolation between `x4v3` and `wdn-x4v3` becomes
   important, add a thin Python wrapper around `inference_realesrgan.py`
   that the pipeline can fall back to via `MODEL=python:realesr-general-x4v3:0.4`
   or similar. Probably not worth it for this flow.

---

## Sources

- Real-ESRGAN docs (anime video model, general-x4v3 release notes)
- nihui's `realcugan-ncnn-vulkan` and `waifu2x-ncnn-vulkan` READMEs
- *Investigating Tradeoffs in Real-World Video Super-Resolution*
  (RealBasicVSR, CVPR 2022)
- *VideoGigaGAN: Towards Detail-rich Video Super-Resolution* (CVPR 2025)
- *SeedVR* (CVPR 2025) and *SeedVR2: One-Step Video Restoration via
  Diffusion Adversarial Post-Training* (ICLR 2026)
- ComfyUI-SeedVR2 community notes on MPS support and CLI memory issues
- Phoronix RX 9060 XT Linux + ROCm 6.4.1 reviews
- Mesa 26.2 VPE 2.0 announcement
- Apple Silicon upscaler ecosystem: Ron Regev's CoreML guide, PiperSR,
  Unsqueeze, myUpscaler
