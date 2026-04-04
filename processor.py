from PIL import Image, ImageEnhance

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

if __name__ == "__main__":
    # Test stub
    img = Image.new("RGB", (1280, 500), color=(128, 128, 128))
    out = process_image(img, "eink")
    out.save("test_eink.png")
    print(f"Test e-ink processing finished. Output size: {out.size}, Mode: {out.mode}")
