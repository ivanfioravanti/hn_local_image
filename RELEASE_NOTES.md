# Release Notes

## [0.4.0] - 2026-06-15

### Default Generate Command and Compare Grid Cleanup

**Changes:**
- **Default Generate Command:** `generate` now runs by default when no
  subcommand is provided, so documented examples like `uv run main.py --target
  eink` work as expected while `compare`, `install-skill`, `--help`, and
  `--version` remain explicit.
- **Comparison Watermark Fix:** `comparison-grid.png` now uses clean generated
  images for the grid badge, avoiding duplicate watermarks when `compare
  --watermark` is used.

## [0.3.2] - 2026-06-15

### Memory Preflight Checks

**Changes:**
- **Generation Memory Check:** Before loading each image model, the CLI now
  prints available system memory and a model-specific recommendation.
- **Ideogram Warning:** `ideogram-4-fp8` receives the highest advisory memory
  recommendation because it is the most memory-intensive model.

## [0.3.1] - 2026-06-15

### Faster Ideogram Default and Stacked Compare Grid

**Changes:**
- **Ideogram Turbo Default:** `ideogram-4-fp8` now uses the `V4_TURBO_12`
  preset by default for faster generation.
- **Stacked Comparison Grid:** `comparison-grid.png` now promotes Ideogram to a
  centered top row and distributes the remaining models in two-column rows
  below it.

## [0.3.0] - 2026-06-15

### Agent Skill and Model Comparison Contact Sheet

This release adds first-class agent support and improves the `compare` output
for visual model evaluation.

**Features:**
- **Bundled Agent Skill:** Ships an `hn-local-image` Codex skill inside the PyPI
  package so agents can learn the preferred `uvx hn-local-image` workflows.
- **Skill Installer:** Adds `hn-local-image install-skill`, with
  `uvx hn-local-image install-skill` as the recommended way to install the
  bundled skill into `${CODEX_HOME:-~/.codex}/skills`.
- **Comparison Contact Sheet:** The `compare` command now creates a
  `comparison-grid.png` per style, combining all generated model outputs into a
  single image with model watermarks and generation-time stats.
- **Compare Sidecar Metadata:** Per-style and aggregate comparison JSON now
  includes the generated contact-sheet path.

**Installation:**
```bash
uvx hn-local-image install-skill
```

## [0.1.0] - 2025-01-XX

### Initial Release

First stable release of hn-local-image, a tool for generating daily AI art from Hacker News headlines using 100% local Apple Silicon hardware.

**Features:**
- **Multiple Image Models:** Supports `z-image-turbo` (default), FLUX.2 Klein (4B/9B), Ernie Image Turbo, and Ideogram 4 FP8
- **Six Artistic Styles:** editorial, story_scene, story_blueprint, story_desk, story_frontpage, and original
- **Dual Output Targets:** Full-color web output (1280×768) and optimized e-ink monochrome (800×480)
- **Model Comparison:** Built-in `compare` command for side-by-side model evaluation
- **Terminal Preview:** Automatic inline image preview in Kitty and Ghostty terminals
- **Headless Upload:** Optional webhook upload for automation/cron jobs
- **100% Local:** All inference runs on your Apple Silicon Mac via MLX

**Installation:**
```bash
uvx hn-local-image          # Run directly
uv tool install hn-local-image  # Install for persistent use
```

**Requirements:**
- Apple Silicon Mac (M1/M2/M3/M4)
- Python 3.12+
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

**Usage:**
```bash
hn-local-image                              # Default: editorial style, web output
hn-local-image --target eink                # E-ink optimized output
hn-local-image compare --all-styles         # Compare all models across all styles
```

**Credits:**
Built upon the excellent work of:
- [hn_dailyimage](https://github.com/LyalinDotCom/hn_dailyimage) - Original concept
- [MFlux](https://github.com/filipstrand/mflux) - MLX image generation engine
- [mlx-vlm](https://github.com/Blaizzy/mlx-vlm) - MLX vision-language models
