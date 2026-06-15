import typer
import os
import gc
import time
import json
import base64
import random
import subprocess
import sys
import shutil
import requests
import tomllib
import typer._click.exceptions as click_exceptions
from PIL import Image, ImageDraw, ImageFont
from typing import Optional
from pathlib import Path
from io import BytesIO
from dotenv import load_dotenv
from importlib import resources
from importlib.metadata import PackageNotFoundError, version as package_version

from fetcher import fetch_hn_headlines
from prompter import generate_prompt, STYLES, TARGET_PROFILES
from generator import generate_local_image, IMAGE_MODELS
from processor import process_image, add_watermark

# Load base .env first
load_dotenv()

def get_package_version() -> str:
    try:
        return package_version("hn-local-image")
    except PackageNotFoundError:
        try:
            with open(Path(__file__).with_name("pyproject.toml"), "rb") as file:
                return tomllib.load(file)["project"]["version"]
        except Exception:
            return "unknown"

__version__ = get_package_version()

app = typer.Typer(help=f"hn-local-image {__version__}: Generates daily AI art from Hacker News headlines.")

SKILL_NAME = "hn-local-image"
AVAILABLE_IMAGE_MODELS = ", ".join(IMAGE_MODELS.keys())

def version_callback(value: bool):
    if value:
        typer.echo(f"hn-local-image {__version__}")
        raise typer.Exit()

@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Show version and exit.",
    )
):
    pass

def describe_image_model_config(model_config: dict) -> str:
    if "preset" in model_config:
        return f"preset={model_config['preset']}"
    return f"steps={model_config['steps']}, guidance={model_config['guidance']}"

def image_model_label(model_id: str) -> str:
    labels = {
        "z-image-turbo": "Z-Image Turbo",
        "flux2-klein-4b": "FLUX2 Klein 4B",
        "flux2-klein-9b": "FLUX2 Klein 9B",
        "ernie-image-turbo": "Ernie Turbo",
        "ideogram-4-fp8": "Ideogram 4 FP8",
    }
    return labels.get(model_id, model_id)

def load_ui_font(size: int):
    for font_path in (
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "arial.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            continue
    return ImageFont.load_default()

def fit_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    ellipsis = "..."
    for end in range(len(text), 0, -1):
        candidate = text[:end].rstrip() + ellipsis
        if draw.textbbox((0, 0), candidate, font=font)[2] <= max_width:
            return candidate
    return ellipsis

def add_comparison_badge(
    image: Image.Image,
    *,
    model_id: str,
    elapsed_seconds: float,
) -> Image.Image:
    img = image.convert("RGBA")
    draw = ImageDraw.Draw(img, "RGBA")
    label_font = load_ui_font(18)
    meta_font = load_ui_font(15)

    max_text_w = min(img.width - 44, 260)
    model_text = fit_text(draw, image_model_label(model_id), label_font, max_text_w)
    elapsed_text = fit_text(draw, f"{elapsed_seconds:.1f}s", meta_font, max_text_w)

    model_bbox = draw.textbbox((0, 0), model_text, font=label_font)
    elapsed_bbox = draw.textbbox((0, 0), elapsed_text, font=meta_font)
    text_w = max(model_bbox[2] - model_bbox[0], elapsed_bbox[2] - elapsed_bbox[0])
    model_h = model_bbox[3] - model_bbox[1]
    elapsed_h = elapsed_bbox[3] - elapsed_bbox[1]

    pad_x = 10
    pad_y = 8
    badge_w = text_w + pad_x * 2
    badge_h = model_h + elapsed_h + pad_y * 2 + 4
    x = img.width - badge_w - 12
    y = img.height - badge_h - 12

    draw.rectangle((x, y, x + badge_w, y + badge_h), fill=(0, 0, 0, 190))
    draw.text((x + pad_x, y + pad_y), model_text, font=label_font, fill=(255, 255, 255, 255))
    draw.text(
        (x + pad_x, y + pad_y + model_h + 4),
        elapsed_text,
        font=meta_font,
        fill=(230, 230, 230, 255),
    )
    return img.convert("RGB")

def create_comparison_grid(
    image_entries: list[dict],
    *,
    target: str,
    style_id: str,
) -> Image.Image | None:
    if not image_entries:
        return None

    thumb_h = 360 if target == "web" else 300
    label_h = 74
    gap = 18
    margin = 24
    bg = (245, 245, 242)
    panel_bg = (255, 255, 255)
    text = (20, 22, 25)
    muted = (80, 84, 90)

    label_font = load_ui_font(22)
    meta_font = load_ui_font(18)
    title_font = load_ui_font(24)

    tiles = []
    for entry in image_entries:
        img = entry["image"].convert("RGB")
        ratio = thumb_h / img.height
        thumb_w = int(img.width * ratio)
        thumb = img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        tiles.append((entry, thumb))

    tile_w = max(thumb.width for _, thumb in tiles)
    sheet_w = margin * 2 + tile_w * len(tiles) + gap * (len(tiles) - 1)
    sheet_h = margin * 2 + 34 + thumb_h + label_h
    sheet = Image.new("RGB", (sheet_w, sheet_h), bg)
    draw = ImageDraw.Draw(sheet)

    draw.text((margin, margin), f"{style_id} model comparison", font=title_font, fill=text)

    y_img = margin + 44
    x = margin
    for entry, thumb in tiles:
        panel = Image.new("RGB", (tile_w, thumb_h + label_h), panel_bg)
        watermarked_thumb = add_comparison_badge(
            thumb,
            model_id=entry["model"],
            elapsed_seconds=entry["elapsed_seconds"],
        )
        panel.paste(watermarked_thumb, ((tile_w - thumb.width) // 2, 0))
        sheet.paste(panel, (x, y_img))

        model_text = fit_text(draw, image_model_label(entry["model"]), label_font, tile_w - 24)
        elapsed_text = fit_text(draw, f"Generated in {entry['elapsed_seconds']:.1f}s", meta_font, tile_w - 24)
        draw.text((x + 12, y_img + thumb_h + 12), model_text, font=label_font, fill=text)
        draw.text((x + 12, y_img + thumb_h + 40), elapsed_text, font=meta_font, fill=muted)

        x += tile_w + gap

    return sheet

def default_codex_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    base_dir = Path(codex_home).expanduser() if codex_home else Path.home() / ".codex"
    return base_dir / "skills"

def copy_resource_tree(source, destination: Path):
    if source.is_dir():
        destination.mkdir(parents=True, exist_ok=True)
        for child in source.iterdir():
            copy_resource_tree(child, destination / child.name)
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())

def bundled_skill_source():
    return resources.files("hn_local_image_assets").joinpath("skills", SKILL_NAME)

@app.command("install-skill")
def install_skill(
    skills_dir: Optional[Path] = typer.Option(
        None,
        "--skills-dir",
        help="Skills root directory. Defaults to ${CODEX_HOME:-~/.codex}/skills.",
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing hn-local-image skill."),
):
    """Install the bundled Codex skill for hn-local-image."""
    target_root = (skills_dir or default_codex_skills_dir()).expanduser()
    target = target_root / SKILL_NAME

    if target.exists() or target.is_symlink():
        if not force:
            typer.echo(f"Skill already exists at {target}. Use --force to overwrite.", err=True)
            raise typer.Exit(1)
        if target.is_symlink() or target.is_file():
            target.unlink()
        else:
            shutil.rmtree(target)

    copy_resource_tree(bundled_skill_source(), target)
    typer.echo(f"Installed {SKILL_NAME} skill to {target}")
    typer.echo("Restart or reload Codex, then ask: Use $hn-local-image ...")

def display_terminal_preview(png_bytes: bytes, max_cols: int = 0) -> bool:
    """Displays the image inline for Kitty/Ghostty terminals."""
    term = os.environ.get("TERM", "").lower()
    term_program = os.environ.get("TERM_PROGRAM", "").lower()

    if not (term_program in ("ghostty", "kitty") or "kitty" in term or "ghostty" in term):
        return False

    if not png_bytes.startswith(b'\x89PNG\r\n\x1a\n'):
        return False

    encoded = base64.b64encode(png_bytes).decode('ascii')

    # Kitty graphics control payload
    control = "f=100,a=T"
    try:
        columns = os.get_terminal_size().columns
        if columns > 0:
            width = min(columns - 2, max_cols) if max_cols > 0 else columns - 2
            control += f",c={max(width, 1)}"
    except Exception:
        pass
        
    chunk_size = 4096
    print("\nTerminal preview:")
    for i in range(0, len(encoded), chunk_size):
        chunk = encoded[i:i+chunk_size]
        has_more = 1 if i + chunk_size < len(encoded) else 0
        prefix = f"m={has_more}"
        if i == 0:
            prefix = f"{control},{prefix}"
        print(f"\x1b_G{prefix};{chunk}\x1b\\", end="")
    print("\n")
    return True

@app.command()
def generate(
    style: str = typer.Option(os.environ.get("PROMPT_MODE", "editorial"), help="Style to generate: " + ", ".join(STYLES.keys())),
    target: str = typer.Option(os.environ.get("TARGET_MODE", "web"), help="Output target: " + ", ".join(TARGET_PROFILES.keys())),
    output_dir: str = typer.Option(os.environ.get("OUTPUT_DIR", "generated"), help="Directory to save the image"),
    headless: bool = typer.Option(False, "--headless", help="Run without interaction"),
    headless_upload: bool = typer.Option(False, "--headless-upload", help="Generate and upload via WEBHOOK_URL"),
    model_name: str = typer.Option("mlx-community/gemma-4-e4b-it-8bit", help="Text model for prompt generation"),
    image_model: str = typer.Option("z-image-turbo", help="Image model to use: " + AVAILABLE_IMAGE_MODELS),
    watermark: bool = typer.Option(False, "--watermark", help="Add model name watermark to image")
):
    if style not in STYLES:
        typer.echo(f"Error: Unknown style '{style}'. Choose from: {list(STYLES.keys())}", err=True)
        raise typer.Exit(1)
        
    if target not in TARGET_PROFILES:
        typer.echo(f"Error: Unknown target '{target}'. Choose from: {list(TARGET_PROFILES.keys())}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Using style: {style}")
    typer.echo(f"Using target: {target}")
    typer.echo(f"Using image model: {image_model}")

    # 1. Fetch Headlines
    typer.echo("Fetching Hacker News front page...")
    try:
        titles = fetch_hn_headlines(max_stories=30)
    except Exception as e:
        typer.echo(f"Error fetching headlines: {e}", err=True)
        raise typer.Exit(1)
    typer.echo(f"Found {len(titles)} stories")

    # 2. Prompt Generation
    typer.echo("Analyzing HN themes with local model...")
    try:
        prompt_result = generate_prompt(titles, style_id=style, target_id=target, model_name=model_name)
    except Exception as e:
        typer.echo(f"Error generating prompt: {e}", err=True)
        raise typer.Exit(1)
        
    img_prompt = prompt_result["image_prompt"]
    typer.echo(f"Image concept: {img_prompt[:120]}...")

    # 3. Image Generation
    typer.echo("Generating image...")
    # Map target size depending on if it's e-ink or web. 
    # MFlux typically expects dimensions to be multiple of 16. 1280x768 is a good 16:9 
    # For eink (800x480), we can just generate at 800x480 as it's a multiple of 16.
    gen_w, gen_h = (800, 480) if target == "eink" else (1280, 768)

    model_config = IMAGE_MODELS.get(image_model)
    if not model_config:
        typer.echo(f"Error: Unknown image model '{image_model}'. Choose from: {list(IMAGE_MODELS.keys())}", err=True)
        raise typer.Exit(1)

    try:
        raw_image = generate_local_image(
            prompt=img_prompt,
            width=gen_w,
            height=gen_h,
            image_model=image_model,
            steps=model_config.get("steps", 9),
            guidance=model_config.get("guidance", 4.0),
            preset=model_config.get("preset"),
        )
    except Exception as e:
        typer.echo(f"Error generating image: {e}", err=True)
        raise typer.Exit(1)

    # 4. Processing
    typer.echo(f"Processing image for {target}...")
    processed_image = process_image(raw_image, target_mode=target)

    # Add watermark if requested
    if watermark:
        processed_image = add_watermark(processed_image, image_model)

    # 5. Output
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
    base_name = f"hn-{timestamp}-{style}-{target}-{image_model}"
        
    img_path = out_dir / f"{base_name}.png"
    json_path = out_dir / f"{base_name}.json"
    
    processed_image.save(img_path)
    typer.echo(f"Saved image to {img_path}")
    
    # Save Sidecar
    sidecar = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "image_path": str(img_path),
        "text_model": model_name,
        "image_model": image_model,
        "image_model_config": model_config,
        "target_mode": target,
        "prompt_details": prompt_result
    }
    
    with open(json_path, "w") as f:
        json.dump(sidecar, f, indent=2)
    typer.echo(f"Saved prompt details to {json_path}")
    
    # Preview
    import io
    buf = io.BytesIO()
    processed_image.save(buf, format="PNG")
    if display_terminal_preview(buf.getvalue()):
        typer.echo("Displayed generated image inline.")
    else:
        typer.echo("Terminal preview skipped (unsupported terminal).")
        
    # Upload
    webhook_url = os.environ.get("WEBHOOK_URL")
    should_upload = False
    
    if headless_upload:
        if not webhook_url:
            typer.echo("Error: WEBHOOK_URL environment variable is required for --headless-upload", err=True)
            raise typer.Exit(1)
        should_upload = True
    elif not headless and webhook_url:
        should_upload = typer.confirm("Upload this image to the configured webhook?", default=False)
        
    if should_upload:
        typer.echo(f"Uploading image to webhook...")
        max_retries = 3
        transient_codes = (500, 502, 503, 504)
        for attempt in range(1, max_retries + 1):
            try:
                resp = requests.post(webhook_url, data=buf.getvalue(), headers={"Content-Type": "image/png"}, timeout=30)
                if resp.status_code in transient_codes and attempt < max_retries:
                    typer.echo(f"Transient error {resp.status_code}, retrying in {2**attempt}s... (attempt {attempt}/{max_retries})")
                    time.sleep(2 ** attempt)
                    continue
                resp.raise_for_status()
                typer.echo(f"Upload successful (Status: {resp.status_code})")
                break
            except Exception as e:
                if attempt == max_retries:
                    status_code = resp.status_code if 'resp' in dir() else 'N/A'
                    response_body = resp.text if 'resp' in dir() else 'N/A'
                    typer.echo(f"Error uploading image: {e} | Status: {status_code} | Body: {response_body}", err=True)
                    raise typer.Exit(1)

def _validate_image_models(image_models: list[str] | None) -> list[str]:
    selected = image_models or list(IMAGE_MODELS.keys())
    unknown = [model for model in selected if model not in IMAGE_MODELS]
    if unknown:
        typer.echo(f"Error: Unknown image model(s) {unknown}. Choose from: {list(IMAGE_MODELS.keys())}", err=True)
        raise typer.Exit(1)
    return selected

def _run_compare(
    styles: list[str],
    target: str,
    output_dir: str,
    model_name: str,
    image_models: list[str] | None = None,
    watermark: bool = False,
):
    """Core compare logic shared between single-style and all-styles modes."""
    if target not in TARGET_PROFILES:
        typer.echo(f"Error: Unknown target '{target}'. Choose from: {list(TARGET_PROFILES.keys())}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Using target: {target}")
    selected_image_models = _validate_image_models(image_models)
    typer.echo(f"Comparing image models: {', '.join(selected_image_models)}")

    # 1. Fetch Headlines (reuse from parent if available)
    headlines_path = os.environ.get("_COMPARE_HEADLINES")
    if headlines_path and Path(headlines_path).exists():
        typer.echo("Loading shared headlines...")
        with open(headlines_path) as f:
            titles = json.load(f)
    else:
        typer.echo("Fetching Hacker News front page...")
        try:
            titles = fetch_hn_headlines(max_stories=30)
        except Exception as e:
            typer.echo(f"Error fetching headlines: {e}", err=True)
            raise typer.Exit(1)
    typer.echo(f"Found {len(titles)} stories")

    # 2. Shared seed for all styles and models
    seed_str = os.environ.get("_COMPARE_SEED")
    if seed_str:
        seed = int(seed_str)
        typer.echo(f"Using shared seed: {seed}")
    else:
        seed = random.randint(0, 2**32 - 1)
        typer.echo(f"Using seed: {seed}")

    gen_w, gen_h = (800, 480) if target == "eink" else (1280, 768)

    # 3. Output root
    timestamp = os.environ.get("_COMPARE_TIMESTAMP") or time.strftime("%Y-%m-%d_%H-%M-%S")
    compare_base = Path(output_dir) / "compare" / timestamp
    compare_base.mkdir(parents=True, exist_ok=True)

    # 4. Generate all prompts first, then free the text model
    style_prompts = {}
    for style_id in styles:
        typer.echo(f"\n{'='*60}")
        typer.echo(f"Style: {style_id}")
        typer.echo(f"{'='*60}")

        typer.echo("Analyzing HN themes with local model...")
        try:
            prompt_result = generate_prompt(titles, style_id=style_id, target_id=target, model_name=model_name)
        except Exception as e:
            typer.echo(f"Error generating prompt: {e}", err=True)
            continue

        img_prompt = prompt_result["image_prompt"]
        typer.echo(f"Image concept: {img_prompt[:120]}...")
        style_prompts[style_id] = prompt_result

    # Free text model memory before loading image models
    gc.collect()

    # 5. Generate images per style
    all_results = {}
    for style_id, prompt_result in style_prompts.items():
        img_prompt = prompt_result["image_prompt"]
        typer.echo(f"\n{'='*60}")
        typer.echo(f"Style: {style_id}")
        typer.echo(f"{'='*60}")

        style_dir = compare_base / style_id
        style_dir.mkdir(parents=True, exist_ok=True)

        results = []
        comparison_entries = []
        for model_id in selected_image_models:
            model_config = IMAGE_MODELS[model_id]
            typer.echo(f"\nGenerating with {model_id} ({describe_image_model_config(model_config)})...")
            t0 = time.time()
            try:
                raw_image = generate_local_image(
                    prompt=img_prompt,
                    width=gen_w,
                    height=gen_h,
                    image_model=model_id,
                    steps=model_config.get("steps", 9),
                    seed=seed,
                    guidance=model_config.get("guidance", 4.0),
                    preset=model_config.get("preset"),
                )
                processed_image = process_image(raw_image, target_mode=target)

                # Add watermark if requested
                if watermark:
                    processed_image = add_watermark(processed_image, model_id)

                img_path = style_dir / f"{model_id}.png"
                processed_image.save(img_path)
                elapsed = time.time() - t0
                typer.echo(f"  Saved {img_path} ({elapsed:.1f}s)")

                comparison_entries.append({
                    "model": model_id,
                    "elapsed_seconds": round(elapsed, 1),
                    "image": processed_image,
                })
                results.append({
                    "model": model_id,
                    "config": model_config,
                    "elapsed_seconds": round(elapsed, 1),
                    "image_path": str(img_path),
                })
            except Exception as e:
                typer.echo(f"  Error with {model_id}: {e}", err=True)
                results.append({"model": model_id, "error": str(e)})

            # Free image model memory before loading the next one
            gc.collect()

        comparison_grid_path = None
        comparison_grid = create_comparison_grid(
            comparison_entries,
            target=target,
            style_id=style_id,
        )
        if comparison_grid is not None:
            comparison_grid_path = style_dir / "comparison-grid.png"
            comparison_grid.save(comparison_grid_path)
            typer.echo(f"  Saved {comparison_grid_path}")
            buf = BytesIO()
            comparison_grid.save(buf, format="PNG")
            typer.echo(f"\n{style_id} comparison:")
            display_terminal_preview(buf.getvalue())

        all_results[style_id] = {
            "prompt_details": prompt_result,
            "models": results,
            "comparison_grid_path": str(comparison_grid_path) if comparison_grid_path else None,
        }

        # Save per-style sidecar
        sidecar = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": seed,
            "text_model": model_name,
            "target_mode": target,
            "image_models": selected_image_models,
            "style": style_id,
            "dimensions": f"{gen_w}x{gen_h}",
            "comparison_grid_path": str(comparison_grid_path) if comparison_grid_path else None,
            "prompt_details": prompt_result,
            "models": results,
        }
        with open(style_dir / "comparison.json", "w") as f:
            json.dump(sidecar, f, indent=2)

    # 6. Save global sidecar with all styles
    global_sidecar = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "seed": seed,
        "text_model": model_name,
        "target_mode": target,
        "image_models": selected_image_models,
        "dimensions": f"{gen_w}x{gen_h}",
        "headlines": titles,
        "styles": all_results,
    }
    with open(compare_base / "comparison.json", "w") as f:
        json.dump(global_sidecar, f, indent=2)
    typer.echo(f"\nComparison complete. Results saved to {compare_base}")


@app.command()
def compare(
    style: str = typer.Option(os.environ.get("PROMPT_MODE", "editorial"), help="Style to generate: " + ", ".join(STYLES.keys())),
    target: str = typer.Option(os.environ.get("TARGET_MODE", "web"), help="Output target: " + ", ".join(TARGET_PROFILES.keys())),
    output_dir: str = typer.Option(os.environ.get("OUTPUT_DIR", "generated"), help="Directory to save images"),
    text_model: str = typer.Option(
        "mlx-community/gemma-4-e4b-it-8bit",
        "--text-model",
        "--model-name",
        help="Text model for prompt generation",
    ),
    image_model: Optional[list[str]] = typer.Option(
        None,
        "--image-model",
        help="Image model to compare. Repeat to compare a subset.",
    ),
    all_styles: bool = typer.Option(False, "--all-styles", help="Generate all styles in a single run with shared headlines and seed"),
    watermark: bool = typer.Option(False, "--watermark", help="Add model name watermark to images")
):
    """Generate one image per image model using the same prompt and seed for comparison."""
    if all_styles:
        # Fetch headlines and seed in the parent process, then spawn a subprocess per style
        # to avoid GPU memory accumulation across model loads.
        if target not in TARGET_PROFILES:
            typer.echo(f"Error: Unknown target '{target}'. Choose from: {list(TARGET_PROFILES.keys())}", err=True)
            raise typer.Exit(1)
        selected_image_models = _validate_image_models(image_model)

        typer.echo(f"Using target: {target}")
        typer.echo(f"Comparing image models: {', '.join(selected_image_models)}")
        typer.echo("Fetching Hacker News front page...")
        try:
            titles = fetch_hn_headlines(max_stories=30)
        except Exception as e:
            typer.echo(f"Error fetching headlines: {e}", err=True)
            raise typer.Exit(1)
        typer.echo(f"Found {len(titles)} stories")

        seed = random.randint(0, 2**32 - 1)
        typer.echo(f"Using shared seed: {seed}")

        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        compare_base = Path(output_dir) / "compare" / timestamp
        compare_base.mkdir(parents=True, exist_ok=True)

        # Write headlines to a temp file so subprocesses reuse them
        headlines_path = compare_base / "_headlines.json"
        with open(headlines_path, "w") as f:
            json.dump(titles, f)

        # Run each style in a subprocess
        styles = list(STYLES.keys())
        failed = []
        for i, style_id in enumerate(styles):
            typer.echo(f"\n[{i+1}/{len(styles)}] Style: {style_id}")
            cmd = [
                "hn-local-image", "compare",
                "--style", style_id,
                "--target", target,
                "--output-dir", output_dir,
                "--text-model", text_model,
            ]
            for model_id in selected_image_models:
                cmd.extend(["--image-model", model_id])
            if watermark:
                cmd.append("--watermark")
            # Pass shared data via environment
            env = os.environ.copy()
            env["_COMPARE_SEED"] = str(seed)
            env["_COMPARE_TIMESTAMP"] = timestamp
            env["_COMPARE_HEADLINES"] = str(headlines_path)

            result = subprocess.run(cmd, env=env)
            if result.returncode != 0:
                typer.echo(f"  Style '{style_id}' failed with exit code {result.returncode}", err=True)
                failed.append(style_id)

        # Clean up temp headlines file
        headlines_path.unlink(missing_ok=True)

        # Build global sidecar from per-style results
        all_results = {}
        for style_id in styles:
            sidecar_path = compare_base / style_id / "comparison.json"
            if sidecar_path.exists():
                with open(sidecar_path) as f:
                    all_results[style_id] = json.load(f)

        global_sidecar = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": seed,
            "text_model": text_model,
            "target_mode": target,
            "image_models": selected_image_models,
            "headlines": titles,
            "styles": all_results,
            "failed": failed,
        }
        with open(compare_base / "comparison.json", "w") as f:
            json.dump(global_sidecar, f, indent=2)

        typer.echo(f"\nComparison complete. Results saved to {compare_base}")
        if failed:
            typer.echo(f"Failed styles: {failed}", err=True)

    elif style in STYLES:
        _run_compare(
            styles=[style],
            target=target,
            output_dir=output_dir,
            model_name=text_model,
            image_models=image_model,
            watermark=watermark,
        )
    else:
        typer.echo(f"Error: Unknown style '{style}'. Choose from: {list(STYLES.keys())}", err=True)
        raise typer.Exit(1)

def run():
    try:
        app(standalone_mode=False)
    except click_exceptions.BadOptionUsage as e:
        option_name = getattr(e, "option_name", None)
        if option_name == "--image-model":
            typer.echo("Error: Option '--image-model' requires an argument.", err=True)
            typer.echo(f"Available image models: {AVAILABLE_IMAGE_MODELS}", err=True)
            raise SystemExit(2)
        e.show()
        raise SystemExit(e.exit_code)
    except click_exceptions.MissingParameter as e:
        param_name = getattr(e.param, "name", None)
        if param_name == "image_model":
            typer.echo("Error: Option '--image-model' requires an argument.", err=True)
            typer.echo(f"Available image models: {AVAILABLE_IMAGE_MODELS}", err=True)
            raise SystemExit(2)
        e.show()
        raise SystemExit(e.exit_code)
    except click_exceptions.Exit as e:
        raise SystemExit(e.exit_code)
    except click_exceptions.ClickException as e:
        e.show()
        raise SystemExit(e.exit_code)

if __name__ == "__main__":
    run()
