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
| `realesrgan-x4plus` | 4× | 33 MB | Live-action, photographic; default for clean 720p / 1080p sources |
| `realesrgan-x4plus-anime` | 4× | 9 MB | Anime stills / lyric-card-style frames |
| `realesr-animevideov3-x2` | 2× | 1.2 MB | Animation video at 2× (preserves temporal consistency) |
| `realesr-animevideov3-x3` | 3× | 1.2 MB | Animation video at 3× |
| `realesr-animevideov3-x4` | 4× | 1.2 MB | Animation video at 4× |

The `realesr-animevideov3-x{2,3,4}` set is one architecture trained for three
different scales; pick the one that matches your `-s`.

License: BSD-3-Clause (Real-ESRGAN upstream).

---

## Recommended add-on: `realesr-general-x4v3`

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
PyTorch model name documented upstream.

| Model name (`-n`) | Scale | Notes |
|---|---|---|
| `realesr-general-x4v3` | 4× (also 1/2/3) | **Best general default for noisy YouTube sources.** Smaller and faster than `x4plus`; supports `-dn 0..1` denoise strength. Use `-dn 0.3–0.5` for typical 480p, `-dn 0.6–1.0` for 240p–360p. |
| `realesr-general-wdn-x4v3` | 4× | "WDN" = stronger denoising twin used by the `-dn` interpolation in the original CLI. The downloader installs it for completeness. |

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
