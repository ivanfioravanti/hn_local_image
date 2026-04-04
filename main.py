import typer
import os
import time
import json
import base64
import requests
from typing import Optional
from pathlib import Path
from io import BytesIO
from dotenv import load_dotenv

from fetcher import fetch_hn_headlines
from prompter import generate_prompt, STYLES, TARGET_PROFILES
from generator import generate_local_image
from processor import process_image

# Load base .env first
load_dotenv()

app = typer.Typer(help="hn-local-image: Generates daily AI art from Hacker News headlines.")

def display_terminal_preview(png_bytes: bytes) -> bool:
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
            control += f",c={max(columns - 2, 1)}"
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
    model_name: str = typer.Option("mlx-community/Qwen3.5-9B-MLX-8bit", help="Text model for prompt generation"),
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
    
    # Configure Fast settings
    steps = 9
    lora_paths = None
    lora_scales = None
    guidance = 4.0
    
    if image_model in ["flux2-klein-4b", "flux2-klein-9b"]:
        steps = 4
        guidance = 1.0
    
    try:
        raw_image = generate_local_image(
            prompt=img_prompt, 
            width=gen_w, 
            height=gen_h, 
            image_model=image_model,
            steps=steps,
            lora_paths=lora_paths,
            lora_scales=lora_scales,
            guidance=guidance
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

if __name__ == "__main__":
    app()
