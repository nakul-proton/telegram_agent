from pathlib import Path
from google import genai
from config import GEMINI_API_KEY, PROJECT_DIR

client = genai.Client(api_key=GEMINI_API_KEY)

PROJECT_DIR = Path(PROJECT_DIR)

MEMORY_FILES = [
    "README.md",
    "CLAUDE.md",
    "memory/project_summary.md",
    "memory/current_state.md",
    "memory/roadmap.md",
    "scripts/lane_detector.py",
    "configs/lane_detection.yaml",
    "tests/test_pipeline.py",
]


def build_project_context():

    context = ""

    for file in MEMORY_FILES:

        path = PROJECT_DIR / file

        if path.exists():

            context += f"\n\n===== {file} =====\n"
            context += path.read_text()

    return context


def ask_gemini(prompt):

    project_context = build_project_context()

    full_prompt = f"""
You are assisting with a software project.

Project Context:
{project_context}

User Request:
{prompt}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=full_prompt
    )

    return response.text
