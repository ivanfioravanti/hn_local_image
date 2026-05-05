import typer
import os
import time
import json
import base64
import random
import subprocess
import sys
import requests
from PIL import Image
from typing import Optional
from pathlib import Path
from io import BytesIO
from dotenv import load_dotenv

from fetcher import fetch_hn_headlines
from prompter import generate_prompt, STYLES, TARGET_PROFILES
from generator import generate_local_image, IMAGE_MODELS
from processor import process_image

# Load base .env first
load_dotenv()

app = typer.Typer(help="hn-local-image: Generates daily AI art from Hacker News headlines.")

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
    model_name: str = typer.Option("mlx-community/Qwen3.5-4B-MLX-8bit", help="Text model for prompt generation"),
    image_model: str = typer.Option("z-image-turbo", help="Image model to use (z-image-turbo, flux2-klein-4b, flux2-klein-9b)")
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
            steps=model_config["steps"],
            guidance=model_config["guidance"],
        )
    except Exception as e:
        typer.echo(f"Error generating image: {e}", err=True)
        raise typer.Exit(1)

    # 4. Processing
    typer.echo(f"Processing image for {target}...")
    processed_image = process_image(raw_image, target_mode=target)
    
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

def _run_compare(styles: list[str], target: str, output_dir: str, model_name: str):
    """Core compare logic shared between single-style and all-styles modes."""
    if target not in TARGET_PROFILES:
        typer.echo(f"Error: Unknown target '{target}'. Choose from: {list(TARGET_PROFILES.keys())}", err=True)
        raise typer.Exit(1)

    typer.echo(f"Using target: {target}")

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

    # 4. Loop over styles
    all_results = {}
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

        style_dir = compare_base / style_id
        style_dir.mkdir(parents=True, exist_ok=True)

        # 5. Generate one image per model
        results = []
        style_images = []
        for model_id, model_config in IMAGE_MODELS.items():
            typer.echo(f"\nGenerating with {model_id} (steps={model_config['steps']}, guidance={model_config['guidance']})...")
            t0 = time.time()
            try:
                raw_image = generate_local_image(
                    prompt=img_prompt,
                    width=gen_w,
                    height=gen_h,
                    image_model=model_id,
                    steps=model_config["steps"],
                    seed=seed,
                    guidance=model_config["guidance"],
                )
                processed_image = process_image(raw_image, target_mode=target)

                img_path = style_dir / f"{model_id}.png"
                processed_image.save(img_path)
                elapsed = time.time() - t0
                typer.echo(f"  Saved {img_path} ({elapsed:.1f}s)")

                style_images.append(processed_image)
                results.append({
                    "model": model_id,
                    "steps": model_config["steps"],
                    "guidance": model_config["guidance"],
                    "elapsed_seconds": round(elapsed, 1),
                    "image_path": str(img_path),
                })
            except Exception as e:
                typer.echo(f"  Error with {model_id}: {e}", err=True)
                results.append({"model": model_id, "error": str(e)})

        # Show side-by-side preview
        if len(style_images) > 1:
            labels = list(IMAGE_MODELS.keys())
            thumb_h = 384
            thumbs = []
            for img, label in zip(style_images, labels):
                ratio = thumb_h / img.height
                thumb_w = int(img.width * ratio)
                thumbs.append(img.resize((thumb_w, thumb_h), Image.Resampling.LANCZOS))
            composite_w = sum(t.width for t in thumbs) + 20 * (len(thumbs) - 1)
            composite = Image.new("RGB", (composite_w, thumb_h), (30, 30, 30))
            x = 0
            for thumb in thumbs:
                composite.paste(thumb, (x, 0))
                x += thumb.width + 20
            buf = BytesIO()
            composite.save(buf, format="PNG")
            typer.echo(f"\n{style_id} comparison:")
            display_terminal_preview(buf.getvalue(), max_cols=120)
        elif len(style_images) == 1:
            buf = BytesIO()
            style_images[0].save(buf, format="PNG")
            display_terminal_preview(buf.getvalue(), max_cols=80)

        all_results[style_id] = {
            "prompt_details": prompt_result,
            "models": results,
        }

        # Save per-style sidecar
        sidecar = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "seed": seed,
            "text_model": model_name,
            "target_mode": target,
            "style": style_id,
            "dimensions": f"{gen_w}x{gen_h}",
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
    model_name: str = typer.Option("mlx-community/Qwen3.5-4B-MLX-8bit", help="Text model for prompt generation"),
    all_styles: bool = typer.Option(False, "--all-styles", help="Generate all styles in a single run with shared headlines and seed"),
):
    """Generate one image per image model using the same prompt and seed for comparison."""
    if all_styles:
        # Fetch headlines and seed in the parent process, then spawn a subprocess per style
        # to avoid GPU memory accumulation across model loads.
        if target not in TARGET_PROFILES:
            typer.echo(f"Error: Unknown target '{target}'. Choose from: {list(TARGET_PROFILES.keys())}", err=True)
            raise typer.Exit(1)

        typer.echo(f"Using target: {target}")
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
                "uv", "run", "main.py", "compare",
                "--style", style_id,
                "--target", target,
                "--output-dir", output_dir,
                "--model-name", model_name,
            ]
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
            "text_model": model_name,
            "target_mode": target,
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
        _run_compare(styles=[style], target=target, output_dir=output_dir, model_name=model_name)
    else:
        typer.echo(f"Error: Unknown style '{style}'. Choose from: {list(STYLES.keys())}", err=True)
        raise typer.Exit(1)

if __name__ == "__main__":
    app()
