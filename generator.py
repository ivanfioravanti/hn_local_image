from PIL import Image
import random

IMAGE_MODELS = {
    "z-image-turbo": {"steps": 9, "guidance": 4.0},
    "flux2-klein-4b": {"steps": 4, "guidance": 1.0},
    # "flux2-klein-9b": {"steps": 4, "guidance": 1.0},  # Disabled: produces noisy output
}

def generate_local_image(
    prompt: str,
    seed: int | None = None,
    width: int = 1280,
    height: int = 500,
    steps: int = 9,
    quantize: int = 8,
    image_model: str = "z-image-turbo",
    lora_paths: list[str] | None = None,
    lora_scales: list[float] | None = None,
    guidance: float = 4.0
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
    else:
        raise ValueError(f"Unknown image model: {image_model}")
    
    print(f"Generating image (seed={seed}, size={width}x{height}, steps={steps}, guidance={guidance})...")
    image = model.generate_image(
        prompt=prompt,
        seed=seed,
        num_inference_steps=steps,
        width=width,
        height=height,
        guidance=guidance,
    )
    
    return image.image

if __name__ == "__main__":
    prompt = "In a futuristic city skyline, a Mac mini stands at the center, symbolizing the core of innovation."
    img = generate_local_image(prompt, width=640, height=250)
    img.save("test_output.png")
    print("Saved test_output.png")
