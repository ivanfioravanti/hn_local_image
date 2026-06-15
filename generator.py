from PIL import Image
import random
import gc
from typing import Any

IMAGE_MODELS = {
    "z-image-turbo": {"steps": 9, "guidance": 4.0},
    "flux2-klein-4b": {"steps": 4, "guidance": 1.0},
    "flux2-klein-9b": {"steps": 4, "guidance": 1.0},
    "ernie-image-turbo": {"steps": 4, "guidance": 1.0},
    "ideogram-4-fp8": {"preset": "V4_DEFAULT_20"},
}

def build_ideogram_caption(prompt: str | dict[str, Any], *, width: int, height: int) -> str | dict[str, Any]:
    """Wrap a generic art prompt in Ideogram 4's structured caption schema."""
    if isinstance(prompt, dict):
        return prompt

    palette = (
        ["#FFFFFF", "#F2F2F2", "#111111"]
        if width == 800 and height == 480
        else ["#0B1020", "#1F6FEB", "#F59E0B", "#F8FAFC", "#111827"]
    )

    return {
        "high_level_description": prompt,
        "style_description": {
            "aesthetics": "editorial, sophisticated, coherent, readable at a glance",
            "lighting": "controlled cinematic lighting with clear subject separation",
            "medium": "digital_painting",
            "art_style": "polished contemporary editorial illustration, no visible words, no logos, no UI screenshots",
            "color_palette": palette,
        },
        "compositional_deconstruction": {
            "background": "A unified atmospheric setting with generous negative space and no text.",
            "elements": [
                {
                    "type": "obj",
                    "bbox": [70, 80, 930, 920],
                    "desc": prompt,
                }
            ],
        },
    }

def generate_local_image(
    prompt: str | dict[str, Any],
    seed: int | None = None,
    width: int = 1280,
    height: int = 500,
    steps: int = 9,
    quantize: int = 8,
    image_model: str = "z-image-turbo",
    lora_paths: list[str] | None = None,
    lora_scales: list[float] | None = None,
    guidance: float = 4.0,
    preset: str | None = None,
) -> Image.Image:
    """Generates an image using MFlux with the specified model and optional LoRAs."""
    
    if seed is None:
        seed = random.randint(0, 2**32 - 1)
        
    print(f"Loading {image_model} model (quantize={quantize})...")
    if lora_paths:
        print(f"Applying LoRAs: {lora_paths} with scales {lora_scales}")
    
    if image_model == "z-image-turbo":
        from mflux.models.z_image import ZImageTurbo
        model = ZImageTurbo(quantize=quantize, lora_paths=lora_paths, lora_scales=lora_scales)
    elif image_model == "flux2-klein-4b":
        from mflux.models.flux2.variants.txt2img.flux2_klein import Flux2Klein
        from mflux.models.common.config.model_config import ModelConfig
        model = Flux2Klein(quantize=quantize, model_config=ModelConfig.flux2_klein_4b(), lora_paths=lora_paths, lora_scales=lora_scales)
    elif image_model == "flux2-klein-9b":
        from mflux.models.flux2.variants.txt2img.flux2_klein import Flux2Klein
        from mflux.models.common.config.model_config import ModelConfig
        model = Flux2Klein(quantize=quantize, model_config=ModelConfig.flux2_klein_9b(), lora_paths=lora_paths, lora_scales=lora_scales)
    elif image_model == "ernie-image-turbo":
        from mflux.models.ernie_image.variants.txt2img.ernie_image import ErnieImage
        from mflux.models.common.config.model_config import ModelConfig
        model = ErnieImage(quantize=quantize, model_config=ModelConfig.ernie_image_turbo(), lora_paths=lora_paths, lora_scales=lora_scales)
    elif image_model == "ideogram-4-fp8":
        from mflux.models.ideogram4.variants.txt2img.ideogram4 import Ideogram4
        from mflux.models.common.config.model_config import ModelConfig
        model = Ideogram4(quantize=quantize, model_config=ModelConfig.ideogram4_fp8(), lora_paths=lora_paths, lora_scales=lora_scales)
        prompt = build_ideogram_caption(prompt, width=width, height=height)
    else:
        raise ValueError(f"Unknown image model: {image_model}")
    
    if image_model == "ideogram-4-fp8":
        print(f"Generating image (seed={seed}, size={width}x{height}, preset={preset or 'V4_DEFAULT_20'})...")
        image = model.generate_image(
            prompt=prompt,
            seed=seed,
            width=width,
            height=height,
            preset=preset,
            strict_caption_validation=True,
        )
    else:
        print(f"Generating image (seed={seed}, size={width}x{height}, steps={steps}, guidance={guidance})...")
        image = model.generate_image(
            prompt=prompt,
            seed=seed,
            num_inference_steps=steps,
            width=width,
            height=height,
            guidance=guidance,
        )

    result = image.image
    del model
    gc.collect()

    return result

if __name__ == "__main__":
    prompt = "In a futuristic city skyline, a Mac mini stands at the center, symbolizing the core of innovation."
    img = generate_local_image(prompt, width=640, height=250)
    img.save("test_output.png")
    print("Saved test_output.png")
