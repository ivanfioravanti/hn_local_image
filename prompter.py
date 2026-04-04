import json
import re
from typing import Any
import mlx_lm
from mlx_lm import load, generate

SHARED_EINK_ART_DIRECTION = "Global art direction for every style: optimize for a 1-bit 800x480 black-and-white e-ink display. White is the dominant field and black is the accent color. Target roughly 75-85% white area and 15-25% black area. Avoid reverse-video compositions, giant black backgrounds, dense black slabs, full-frame darkness, and newspaper pages packed with body copy. Favor clean white space, bold black linework, silhouettes, outlines, sparse labels, and a composition that still reads clearly after monochrome dithering."
SHARED_WEB_ART_DIRECTION = "Global art direction for every style: optimize for a rich 16:9 web image viewed on modern screens. Use the full tonal range and color where helpful, allow deeper contrast, richer materials, and more atmospheric lighting, but keep the composition readable and attractive as a web hero image. Do not force monochrome, white-dominant, or 1-bit constraints unless the style itself calls for it."

TARGET_PROFILES = {
    "eink": {
        "description": "an 800x480 monochrome e-ink display",
        "direction": SHARED_EINK_ART_DIRECTION
    },
    "web": {
        "description": "a 16:9 web hero image for normal screens",
        "direction": SHARED_WEB_ART_DIRECTION
    }
}

STYLES = {
    "editorial": {
        "system": "You are an editorial art director designing a single cover image. Compress many headlines into one surprising but legible visual metaphor. Prefer one dominant scene, one hero subject, 2-4 supporting motifs, strong silhouette, generous negative space, and no text or logos. Avoid collage clutter, screenshots, dashboards, literal headline lists, and generic cyberpunk. {direction}",
        "user": "Input headlines:\n{headlines}\n\nReturn strict JSON with keys: thesis, mood, motifs, composition, image_prompt.\n\nRequirements for image_prompt:\n- 120 to 180 words\n- one unified scene, not a collage\n- suitable for {frame}\n- no words or letters inside the image\n- eccentric but tasteful, like a magazine cover for hackers\n- keep the composition readable at a glance\n- use at least one unexpected metaphor that connects AI, infrastructure, and real-world stakes"
    },
    "story_scene": {
        "system": "You are a concept artist for a minimalist newspaper front page image. Turn a noisy tech news cycle into a single scene with narrative tension. Be specific, visual, and cinematic. {direction}",
        "user": "These are today's top Hacker News titles:\n{headlines}\n\nReturn strict JSON with keys: why_today_is_interesting, scene, visual_hooks, image_prompt.\n\nThe image_prompt must:\n- describe one scene from a slightly elevated wide angle\n- include a central object, a human-scale reference, and 2-3 symbolic supporting elements\n- feel witty, tense, and contemporary rather than nostalgic retro-tech by default\n- suit {frame}\n- contain zero visible text, numbers, interfaces, or logos\n- be composed for {frame}"
    },
    "story_blueprint": {
        "system": "You are a design director making a beautiful speculative blueprint poster from ten Hacker News stories. Build one coherent technical diagram, not a random collage. Text is allowed as short labels, arrows, module names, and captions, but keep it elegant and sparse. The composition should feel dense, legible, and balanced enough to hang on a wall. {direction}",
        "user": "These are the top Hacker News stories to integrate:\n{headlines}\n\nReturn strict JSON with keys: narrative, modules, composition, image_prompt.\n\nThe image_prompt must:\n- turn the top 10 stories into one dense systems map or impossible machine\n- include one central apparatus and 6-10 labeled modules or callouts\n- allow text labels, arrows, captions, and version-style marks\n- feel like a polished hacker blueprint or research poster, not chaos\n- stay visually pleasing with clear hierarchy and generous breathing room\n- work for {frame}"
    },
    "story_desk": {
        "system": "You are an art director staging a detailed but pleasing hacker workspace scene. The top stories should appear as objects, notes, screens, prototypes, cables, books, diagrams, and artifacts on or around the desk. Text is allowed, but it should feel like intentional ephemera rather than a wall of copy. {direction}",
        "user": "Use these top Hacker News stories:\n{headlines}\n\nReturn strict JSON with keys: atmosphere, featured_objects, composition, image_prompt.\n\nThe image_prompt must:\n- create one desk, lab bench, studio, or control-room scene\n- integrate all 10 stories through physical objects and environmental details\n- allow sticky notes, labels, book spines, screen snippets, and schematic notes\n- feel warm, clever, dense, and aesthetically composed rather than messy\n- preserve strong silhouettes and contrast appropriate for {frame}"
    },
    "story_frontpage": {
        "system": "You are designing a visually pleasing fake newspaper or magazine front page inspired by ten Hacker News stories. Mix a hero illustration with supporting columns, labels, sidebars, captions, and typographic blocks. Text is allowed and should feel designed, not accidental. {direction}",
        "user": "Build a front page from these top Hacker News stories:\n{headlines}\n\nReturn strict JSON with keys: editorial_angle, sections, composition, image_prompt.\n\nThe image_prompt must:\n- feel like a designed tech weekly cover or front page\n- include one hero visual plus supporting sidebars or modules tied to the 10 stories\n- allow headlines, pull quotes, labels, issue numbers, and diagram annotations\n- remain balanced and attractive instead of becoming cluttered\n- work for {frame}"
    },
    "original": {
        "system": "You are an expert AI prompt engineer. Write a prompt based on the provided headlines. Do not output any thinking processes, reasoning, or preamble. Output ONLY the final image generation prompt.",
        "user": "Here are today's top Hacker News stories:\n\n{headlines}\n\nAnalyze these stories and identify the top 3-5 overarching themes or sentiments. Then write a detailed, vivid image prompt for an AI image generator. The image should be a single artistic, geeky, visually striking illustration that captures the mood and essence of today's HN front page. Think: technical editorial illustration, blueprint-style line art, retro-futurism, hacker aesthetics, circuit board motifs. Do not list the stories or include any text in the image. {direction} Output only the image generation prompt, nothing else."
    }
}

def extract_json(text: str) -> dict[str, Any]:
    # Look for json blocks
    match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass
            
    # Fallback: look for first { and last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end+1])
        except json.JSONDecodeError:
            pass
    return {}

def generate_prompt(
    titles: list[str], 
    style_id: str = "editorial", 
    target_id: str = "web", 
    model_name: str = "mlx-community/Qwen3.5-9B-MLX-8bit"
) -> dict[str, Any]:
    
    if style_id not in STYLES:
        raise ValueError(f"Unknown style: {style_id}")
    if target_id not in TARGET_PROFILES:
        raise ValueError(f"Unknown target: {target_id}")
        
    target = TARGET_PROFILES[target_id]
    style = STYLES[style_id]
    
    numbered_titles = [f"{i+1}. {t}" for i, t in enumerate(titles)]
    headlines_text = "\n".join(numbered_titles)
    
    system_prompt = style["system"].format(direction=target["direction"], frame=target["description"])
    user_prompt = style["user"].format(headlines=headlines_text, frame=target["description"], direction=target["direction"])
    
    print(f"Loading text model {model_name}...")
    model, tokenizer = load(model_name)
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    
    # Format according to chat template
    if hasattr(tokenizer, "apply_chat_template"):
        prompt = tokenizer.apply_chat_template(
            messages, 
            tokenize=False, 
            add_generation_prompt=True,
            chat_template_kwargs={"enable_thinking": False}
        )
    else:
        # Fallback if no template
        prompt = f"System: {system_prompt}\nUser: {user_prompt}\nAssistant: "
        
    print(f"Generating prompt concept with {model_name}...")
    
    # We add a stop token or generation kwargs if needed, but the best way to prevent thinking 
    # in Qwen 3.5 Instruct is often to append the start of the JSON block directly 
    # so it skips the thinking preamble, or add a strict directive.
    if style_id != "original":
        prompt += "{"
        
    response = generate(model, tokenizer, prompt=prompt, max_tokens=1000, verbose=False)
    
    if style_id != "original":
        response = "{" + response
        
    result = {
        "mode": style_id,
        "headlines": titles,
        "raw_text_output": response,
        "image_prompt": ""
    }
    
    # Strip thinking blocks from the raw response
    clean_response = response
    if "</think>" in clean_response:
        # If the model output a closing think tag (even if we skipped the opening one by appending '{')
        parts = clean_response.split("</think>", 1)
        clean_response = parts[-1].strip()
    elif "<think>" in clean_response and "</think>" in clean_response:
        clean_response = re.sub(r"<think>.*?</think>", "", clean_response, flags=re.DOTALL).strip()
    elif "Thinking Process:" in clean_response:
        parts = clean_response.split("\n\n", 1)
        if len(parts) > 1:
            clean_response = parts[-1].strip()
            
    if style_id == "original":
        # Extract from text directly
        result["image_prompt"] = clean_response
    else:
        parsed = extract_json(clean_response)
        result["structured_output"] = parsed
        if "image_prompt" in parsed:
            result["image_prompt"] = parsed["image_prompt"]
        else:
            # Fallback
            result["image_prompt"] = clean_response
            
    return result

if __name__ == "__main__":
    test_titles = [
        "Show HN: European alternatives to Google, Apple, Dropbox and 120 US apps",
        "Show HN: Apfel – The free AI already on your Mac",
        "April 2026 TLDR Setup for Ollama and Gemma 4 26B on a Mac mini",
        "Google releases Gemma 4 open models"
    ]
    res = generate_prompt(test_titles, style_id="editorial", target_id="web")
    print("\n--- Result Image Prompt ---\n")
    print(res["image_prompt"])
