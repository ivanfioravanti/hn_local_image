# Release Notes

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
