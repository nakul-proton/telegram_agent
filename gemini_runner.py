import shutil
from datetime import datetime
from pathlib import Path
from google import genai
from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    PROJECT_DIR,
)
import subprocess

client = genai.Client(api_key=GEMINI_API_KEY)

PROJECT_DIR = Path(PROJECT_DIR)

MEMORY_FILES = [
    "README.md",
    "CLAUDE.md",
    "memory/project_summary.md",
    "memory/current_state.md",
    "memory/roadmap.md",
    "memory/session_notes.md",
    "requirements.txt",
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
        model=GEMINI_MODEL,
        contents=full_prompt
    )

    return response.text

def build_file(task):

    project_context = build_project_context()

    prompt = f"""
You are a senior Python engineer.

Project Context:
{project_context}

Task:
{task}

IMPORTANT:
Return ONLY the complete contents of the updated
scripts/lane_detector.py file.

Do not explain.
Do not use markdown.
Do not use ```.

Return only Python code.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    generated_dir = Path.home() / "telegram_agent" / "generated"

    generated_dir.mkdir(exist_ok=True)

    output_file = generated_dir / "lane_detector.py"

    output_file.write_text(response.text)

    return str(output_file)

def approve_build():

    project_file = (
        Path(PROJECT_DIR)
        / "scripts"
        / "lane_detector.py"
    )

    generated_file = (
        Path.home()
        / "telegram_agent"
        / "generated"
        / "lane_detector.py"
    )

    if not generated_file.exists():

        return "No generated file found."

    backup_dir = (
        Path.home()
        / "telegram_agent"
        / "backups"
    )

    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = (
        backup_dir
        / f"lane_detector_{timestamp}.py"
    )

    shutil.copy2(
        project_file,
        backup_file
    )

    shutil.copy2(
        generated_file,
        project_file
    )

    return (
        f"Approved.\n"
        f"Backup: {backup_file}\n"
        f"Updated: {project_file}"
    )

def run_pytest():

    try:

        result = subprocess.run(
            ["pytest"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )

        output = result.stdout + "\n" + result.stderr

        return output

    except Exception as e:

        return f"Pytest Error:\n{e}"
