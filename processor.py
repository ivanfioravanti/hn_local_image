from PIL import Image, ImageEnhance, ImageDraw, ImageFont

def process_image(img: Image.Image, target_mode: str = "web") -> Image.Image:
    """Processes the image according to the target mode ('web' or 'eink')."""
    if target_mode == "web":
        # For web, return as is (could resize if needed)
        return img
    elif target_mode == "eink":
        return render_eink_png(img, 800, 480)
    else:
        raise ValueError(f"Unknown target mode: {target_mode}")

def render_eink_png(img: Image.Image, target_w: int = 800, target_h: int = 480) -> Image.Image:
    """
    Renders an image optimized for a monochrome e-ink display using Pillow.
    We resize, convert to grayscale, boost contrast/brightness, and apply Floyd-Steinberg dithering.
    """
    # Resize first using high-quality resampling
    resized = img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    # Convert to grayscale
    gray = resized.convert("L")
    
    # Enhance contrast to make blacks blacker and whites whiter
    contrast = ImageEnhance.Contrast(gray)
    high_contrast = contrast.enhance(1.5)  # Boost contrast
    
    # Enhance brightness to favor white space for e-ink
    brightness = ImageEnhance.Brightness(high_contrast)
    brightened = brightness.enhance(1.2)  # Boost brightness slightly
    
    # Convert to 1-bit monochrome with Floyd-Steinberg dithering
    dithered = brightened.convert("1", dither=Image.Dither.FLOYDSTEINBERG)
    
    return dithered

def add_watermark(image: Image.Image, model_name: str) -> Image.Image:
    """Adds model name watermark to the bottom-right corner of the image."""
    # Work on a copy to avoid modifying the original
    img = image.copy()

    # Convert to RGB if necessary (for e-ink mode images)
    if img.mode != 'RGB':
        img = img.convert('RGB')

    # Create a drawing context
    draw = ImageDraw.Draw(img)

    # Try to load a system font, fall back to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 20)
        except:
            font = ImageFont.load_default()

    # Prepare text - use short model names
    short_names = {
        "z-image-turbo": "Z-Image Turbo",
        "flux2-klein-4b": "FLUX2 Klein 4B",
        "flux2-klein-9b": "FLUX2 Klein 9B",
        "ernie-image-turbo": "Ernie Turbo",
        "ideogram-4-fp8": "Ideogram 4 FP8",
    }
    text = short_names.get(model_name, model_name)

    # Get text bounding box
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]

    # Position in bottom-right corner with padding
    padding = 8
    x = img.width - text_width - padding
    y = img.height - text_height - padding

    # Draw semi-transparent background rectangle
    draw.rectangle([x-4, y-4, x+text_width+4, y+text_height+4],
                  fill=(0, 0, 0))

    # Draw text in white
    draw.text((x, y), text, font=font, fill=(255, 255, 255))

    return img

if __name__ == "__main__":
    # Test stub
    img = Image.new("RGB", (1280, 500), color=(128, 128, 128))
    out = process_image(img, "eink")
    out.save("test_eink.png")
    print(f"Test e-ink processing finished. Output size: {out.size}, Mode: {out.mode}")
