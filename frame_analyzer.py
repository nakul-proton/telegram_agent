from pathlib import Path
from google import genai

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    PROJECT_DIR,
)

client = genai.Client(api_key=GEMINI_API_KEY)


def analyze_frames():

    frames_dir = (
        Path(PROJECT_DIR)
        / "output"
        / "frames"
        / "road_video"
    )

    image_files = [
        frames_dir / "frame_000100_mask.png",
        frames_dir / "frame_000100_roi.png",
        frames_dir / "frame_000100_annotated.png",
    ]

    existing = [f for f in image_files if f.exists()]

    if not existing:
        return "No frame images found."

    prompt = """
Analyze these lane detection outputs.

Please answer:

1. Is the mask quality acceptable?
2. Is the ROI correctly positioned?
3. Are lane markings preserved?
4. What should be improved next?
5. Should ROI tuning happen before temporal smoothing?

Be specific.
"""

    parts = [prompt]

    for image in existing:
        parts.append(image)

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=parts,
    )

    return response.text
