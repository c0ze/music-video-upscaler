# Models

`realesrgan-ncnn-vulkan` loads two files per model from this directory:

- `<name>.param` — network description (text)
- `<name>.bin` — weights (binary)

You select the model by passing its `<name>` (without the extension) as the
`MODEL` argument to `03_upscale.sh` / `windows\03_upscale.ps1` / `upscale_video.*`,
which forwards it to the binary as `-n <name>`.

> Windows note: Real-ESRGAN resolves `models/` relative to its **current
> working directory**. The pipeline scripts `cd` to the repository root before
> launching the binary, so `models/` always resolves correctly regardless of
> where you launched the script from.

## Auto-install

```bash
# Linux / macOS — base + realesr-general-x4v3 (recommended)
./download_models.sh

# Windows
.\windows\download-models.ps1
```

See [Downloader options](#downloader-options) below.

---

## Bundled models (base set)

These ship inside the official Real-ESRGAN ncnn-vulkan v0.2.5.0 release zip
([xinntao/Real-ESRGAN releases](https://github.com/xinntao/Real-ESRGAN/releases/tag/v0.2.5.0)).
Source archive (any platform; identical models inside):

- https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-ubuntu.zip
- https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-macos.zip
- https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip

| Model name (`-n`) | Scale | Size | Best for |
|---|---|---|---|
| `realesrgan-x4plus` | 4× | 33 MB | Live-action, photographic; only when the source is genuinely clean (BD/DVD remasters, official-channel 1080p) |
| `realesrgan-x4plus-anime` | 4× | 9 MB | Anime stills / lyric-card-style frames |
| `realesr-animevideov3-x2` | 2× | 1.2 MB | Animation video at 2× (preserves temporal consistency) |
| `realesr-animevideov3-x3` | 3× | 1.2 MB | Animation video at 3× |
| `realesr-animevideov3-x4` | 4× | 1.2 MB | Animation video at 4× |

The `realesr-animevideov3-x{2,3,4}` set is one architecture trained for three
different scales; pick the one that matches your `-s`.

License: BSD-3-Clause (Real-ESRGAN upstream).

---

## Pipeline default: `realesr-general-x4v3`

This is now the **default model** used by `03_upscale.sh`, `upscale_video.sh`,
`run_pipeline.sh`, and their PowerShell counterparts. It handles real-world
YouTube degradation (re-encoding, blocky compression, mosquito noise) much
better than `realesrgan-x4plus` and won't over-sharpen halos around stage
lighting or drum kits.

xinntao publishes this model only as PyTorch weights
([`realesr-general-x4v3.pth`](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-x4v3.pth),
[`realesr-general-wdn-x4v3.pth`](https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesr-general-wdn-x4v3.pth)).
The community-converted ncnn versions used by Upscayl are mirrored at
[upscayl/custom-models](https://github.com/upscayl/custom-models):

- https://raw.githubusercontent.com/upscayl/custom-models/main/models/RealESRGAN_General_x4_v3.bin
- https://raw.githubusercontent.com/upscayl/custom-models/main/models/RealESRGAN_General_x4_v3.param
- https://raw.githubusercontent.com/upscayl/custom-models/main/models/RealESRGAN_General_WDN_x4_v3.bin
- https://raw.githubusercontent.com/upscayl/custom-models/main/models/RealESRGAN_General_WDN_x4_v3.param

The downloader renames them to `realesr-general-x4v3.{bin,param}` and
`realesr-general-wdn-x4v3.{bin,param}` so the `-n` argument matches the
PyTorch model name documented upstream. Both files are tracked in this repo
(roughly 5 MB total) so a fresh clone has working defaults.

| Model name (`-n`) | Scale | Notes |
|---|---|---|
| `realesr-general-x4v3` | 4× | **Pipeline default.** Best general model for compressed sources. Smaller and faster than `x4plus`. |
| `realesr-general-wdn-x4v3` | 4× | "WDN" twin = stronger denoising. Use this for 240p–360p YouTube where the v3 model still leaves visible blocking. Pass via `MODEL=realesr-general-wdn-x4v3` (POSIX) or `-Model realesr-general-wdn-x4v3` (PowerShell). |

> **Why no `-dn` flag?** xinntao's PyTorch CLI (`inference_realesrgan.py`)
> exposes `-dn 0.0..1.0` to interpolate at runtime between the v3 and WDN
> weights. The standalone `realesrgan-ncnn-vulkan` binary (which this pipeline
> uses) does **not** implement that flag — see the binary's `-h` output. To get
> the equivalent on ncnn, switch the model name itself: pick `v3` for less
> denoise, `wdn-v3` for more. If you need fine-grained interpolation, run the
> Python pipeline directly.

License: BSD-3-Clause (weights), conversion script is community-maintained.

---

## Optional: extra community models

`./download_models.sh --extras` adds higher-quality general-purpose models from
[upscayl/custom-models](https://github.com/upscayl/custom-models). They use the
same SRVGGNet / RRDBNet ncnn architecture and "just work" with our pipeline.

| Model name (`-n`) | Scale | Notes |
|---|---|---|
| `4xLSDIR` | 4× | Trained on the LSDIR dataset; very strong on photographic content. Heavier than `realesrgan-x4plus`. |
| `4xNomos8kSC` | 4× | Trained on Nomos 8K dataset, "SC" = sharp & clean. Good for relatively clean 720p sources. |

Each upstream model carries its own license (most are Apache-2.0 or
BSD-3-Clause). Check the upscayl repo for specifics before redistribution.

---

## Adding your own models

Drop any compatible `<name>.param` / `<name>.bin` pair into this directory and
invoke with `-Model <name>` (PowerShell) or as the 4th argument to
`./03_upscale.sh` (POSIX). Compatible model architectures: SRVGGNet,
RRDBNet, ESRGAN, RealESRGAN, and any model exported through `pnnx` to the
ncnn `.param`/`.bin` format.

For a wider catalog, see the [OpenModelDB](https://openmodeldb.info/) project
and the [Upscale Wiki](https://upscale.wiki/wiki/Main_Page).

---

## Downloader options

```text
./download_models.sh [options]

  (no args)        install base set + realesr-general-x4v3 (recommended)
  --base-only      install only the xinntao bundled set
  --no-general     skip realesr-general-x4v3 / -wdn-x4v3
  --extras         additionally install community extras (4xLSDIR, 4xNomos8kSC)
  --force          redownload even if files already exist
  --list           list models currently present in models/
  -h, --help       show this help and exit
```

Equivalent PowerShell flags: `-BaseOnly`, `-NoGeneral`, `-Extras`, `-Force`,
`-List`.

The script is idempotent: existing non-empty files are kept unless `--force`
is passed. It only requires `curl` and `unzip` (both checked in
`install-dependencies.sh`).

---

## Files in this directory

Tracked via git (so a fresh clone has working defaults):

```
realesrgan-x4plus.{bin,param}
realesrgan-x4plus-anime.{bin,param}
realesr-animevideov3-x{2,3,4}.{bin,param}
```

Anything you fetch via `--no-general --extras` etc. is left untracked unless
you explicitly add it. See `.gitignore` if you want to keep extra weights out
of version control.
