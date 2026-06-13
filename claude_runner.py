import subprocess
from config import PROJECT_DIR_DEFAULT

PROJECT_DIR = PROJECT_DIR_DEFAULT

def ask_claude(prompt):

    print(f"Running Claude with: {prompt}")

    result = subprocess.run(
        ["claude", "-p", prompt],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=1800
    )

    print("STDOUT:")
    print(result.stdout)

    if "Credit balance is too low" in result.stdout:
        return "Claude API credits exhausted."

    print("STDERR:")
    print(result.stderr)

    return result.stdout


def build_with_claude(prompt):

    print(f"Building with Claude: {prompt}")

    result = subprocess.run(
        [
            "claude",
            "-p",
            prompt,
            "--permission-mode",
            "bypassPermissions"
        ],
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=1800
    )

    print("STDOUT:")
    print(result.stdout)

    if "Credit balance is too low" in result.stdout:
        return "Claude API credits exhausted."

    print("STDERR:")
    print(result.stderr)

    return result.stdout

    
