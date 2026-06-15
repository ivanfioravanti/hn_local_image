---
name: hn-local-image
description: Use the hn-local-image PyPI package to generate AI artwork from Hacker News headlines on local Apple Silicon. Use when the user asks to run hn-local-image, create HN/front-page/news headline artwork, generate web or e-ink images from Hacker News, compare supported local image models, configure headless uploads, or automate this package from an agent.
---

# HN Local Image

## Overview

Use `hn-local-image` as a CLI-first package for turning current Hacker News stories into generated images. Prefer the released PyPI package for normal usage; only clone or edit the source repo when the user asks for development work.

The package runs local MLX-based inference and is intended for Apple Silicon Macs with Python 3.12+. Expect first runs to download model weights and take substantially longer than later runs.

## Quick Start

Prefer `uvx` when the user wants to run the package without installing it:

```bash
uvx hn-local-image
```

Use a persistent tool install when the user wants repeated use:

```bash
uv tool install hn-local-image
hn-local-image
```

## Common Tasks

Generate the default color web image:

```bash
uvx hn-local-image
```

Generate an e-ink optimized monochrome image:

```bash
uvx hn-local-image --target eink
```

Select a style:

```bash
uvx hn-local-image --style story_blueprint
```

Select an image model:

```bash
uvx hn-local-image --image-model flux2-klein-9b
```

Compare image models with one shared prompt and seed:

```bash
uvx hn-local-image compare --style editorial --watermark
```

Compare all styles for e-ink output:

```bash
uvx hn-local-image compare --all-styles --target eink
```

Run headless and upload the PNG bytes to a webhook:

```bash
WEBHOOK_URL=https://example.com/upload uvx hn-local-image --target eink --headless-upload
```

## Options To Prefer

- Use `--target web` for full-color 1280x768 PNG output; this is the default.
- Use `--target eink` for 800x480 1-bit dithered output intended for e-ink displays.
- Use `--style editorial` for the default style.
- Other styles are `story_scene`, `story_blueprint`, `story_desk`, `story_frontpage`, and `original`.
- Image models are `z-image-turbo`, `flux2-klein-4b`, `flux2-klein-9b`, `ernie-image-turbo`, and `ideogram-4-fp8`.
- Use `--output-dir <dir>` when the user needs files in a specific location; otherwise outputs go under `generated/`.
- Use `--model-name <hf-repo-id>` only when the user asks to change the local text model used for prompt generation.
- Use `--watermark` for model comparisons or visual reports where the chosen image model should be visible in the output.

## Agent Workflow

1. Confirm the user is on an Apple Silicon Mac before running full generation when hardware is unclear.
2. Prefer a help or dry command first if package availability is uncertain:

```bash
uvx hn-local-image --help
```

3. Warn before full generation if it may download large model files or take a long time.
4. After generation, report the produced PNG path and JSON sidecar path. Do not paste the generated JSON unless the user asks.
5. For automation, recommend environment variables only for stable defaults:

```env
WEBHOOK_URL=https://example.com/upload
PROMPT_MODE=editorial
TARGET_MODE=eink
OUTPUT_DIR=generated
HN_URL=https://news.ycombinator.com/
```

## Failure Handling

- If `uvx` cannot find the package, check that the package name is `hn-local-image`.
- If model loading fails, verify Apple Silicon, Python 3.12+, available disk space, and network access for initial model downloads.
- If webhook upload fails, verify `WEBHOOK_URL`, network access, and that the endpoint accepts raw `image/png` request bodies.
- If the user asks to change package behavior or CLI flags, switch to source-repo development rather than treating it as package usage.
