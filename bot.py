import asyncio
from urllib import response
from claude_runner import ask_claude, build_with_claude
from gemini_runner import (
    ask_gemini,
    build_file,
    approve_build,
    build_project,
    run_pytest,
)
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pathlib import Path
from config import BOT_TOKEN
from frame_analyzer import analyze_frames
from gemini_runner import rollback_latest_backup
from build_parser import (
    get_active_project,
    select_project,
    list_projects,
    get_latest_failed_build,
    read_generated_files_as_text,
)

async def send_long_message(update, text):

    MAX_LEN = 3900

    chunks = [
        text[i:i + MAX_LEN]
        for i in range(0, len(text), MAX_LEN)
    ]

    for idx, chunk in enumerate(chunks, start=1):

        if len(chunks) > 1:
            chunk = f"[Part {idx}/{len(chunks)}]\n\n" + chunk

        await update.message.reply_text(chunk)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hello Nakul! Telegram Agent is running."
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Agent Status: ONLINE"
    )

async def agent(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/agent your question"
        )
        return

    prompt = " ".join(context.args)

    await update.message.reply_text(
        "Thinking..."
    )

    try:
        response = await asyncio.to_thread(
            ask_claude,
            prompt
        )

        await send_long_message(
            update,
            response
        )

    except Exception as e:
        await update.message.reply_text(
            f"Agent Error:\n{str(e)}"
        )

async def gemini(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/gemini your question"
        )
        return

    prompt = " ".join(context.args)

    await update.message.reply_text(
        "Thinking with Gemini..."
    )

    try:
        response = await asyncio.to_thread(
            ask_gemini,
            prompt
        )

        await send_long_message(
            update,
            response
        )

    except Exception as e:
        await update.message.reply_text(
            f"Gemini Error:\n{str(e)}"
        )

def list_project_files():
    """List files from active project"""
    
    project = get_active_project()
    project_dir = Path(project["path"])

    important_paths = [
        "README.md",
        "CLAUDE.md",
        "requirements.txt",
        "configs",
        "memory",
        "scripts",
        "tests"
    ]

    files = []

    for item in important_paths:

        path = project_dir / item

        if not path.exists():
            continue

        if path.is_file():

            files.append(item)

        else:

            for f in sorted(path.rglob("*")):

                if not f.is_file():
                    continue

                # Skip cache files
                if "__pycache__" in f.parts:
                    continue

                if ".pytest_cache" in f.parts:
                    continue

                if f.suffix == ".pyc":
                    continue

                files.append(
                    str(f.relative_to(project_dir))
                )

    return "\n".join(files)

async def project_files(update: Update,
                        context: ContextTypes.DEFAULT_TYPE):

    files = list_project_files()

    await send_long_message(
        update,
        files
    )

async def build(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not context.args:
        await update.message.reply_text(
            "Usage:\n/build your request"
        )
        return

    prompt = " ".join(context.args)

    await update.message.reply_text(
        "Building..."
    )

    try:
        response = await asyncio.to_thread(
            build_with_claude,
            prompt
        )

        await send_long_message(
            update,
            response
        )

    except Exception as e:
        await update.message.reply_text(
            f"Build Error:\n{str(e)}"
       )

def read_file(relative_path):
    """Read file from active project"""
    
    project = get_active_project()
    path = Path(project["path"]) / relative_path

    if not path.exists():
        return f"File not found: {relative_path}"

    return path.read_text()

async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE):

    content = read_file("memory/project_summary.md")

    await send_long_message(
        update,
        content
    )

async def current_state(update, context):

    content = read_file("memory/current_state.md")

    await send_long_message(
        update,
        content
    )

async def roadmap(update, context):

    content = read_file("memory/roadmap.md")

    await send_long_message(
        update,
        content
    )

REVIEW_PROMPT = """
Review this software project.

Provide:

1. Maturity score
2. Top risks
3. Technical debt
4. Testing gaps
5. Recommended next task
"""

async def review(update, context):

    await update.message.reply_text(
        "Reviewing project..."
    )

    response = await asyncio.to_thread(
        ask_gemini,
        REVIEW_PROMPT
    )

    await send_long_message(
        update,
        response
    )

async def next_task(update: Update,
                    context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "Identifying next task..."
    )

    prompt = """
Based on:
- roadmap.md
- current_state.md
- source code
- tests

Recommend exactly ONE next task.

Explain:
1. Why it should be next
2. Expected benefit
3. Estimated effort (Low/Medium/High)
4. Files likely to change

Provide a clear recommendation.
"""

    response = await asyncio.to_thread(
        ask_gemini,
        prompt
    )

    await send_long_message(
        update,
        response
    )

async def build(update, context):

    task = " ".join(context.args)

    if not task:

        await update.message.reply_text(
            "Usage:\n/build <task>"
        )
        return

    project = get_active_project()
    project_name = project["name"]

    await update.message.reply_text(
        f"Generating build for project: {project_name}..."
    )

    result = await asyncio.to_thread(
        build_project,
        task,
        project
    )

    build_id = result.get("build_id", "unknown")
    files = result["files"]
    status = result.get("status", "unknown")
    error_type = result.get("error_type")

    message = (
        f"Build Complete [{build_id}]\n"
        f"Project: {project_name}\n"
        f"Status: {status}\n\n"
        f"Files Modified: {len(files)}\n\n"
    )

    if error_type:
        message += f"⚠️  Validation Error Type: {error_type}\n\n"

    message += "\n".join(files[:20])

    if len(files) > 20:
        message += f"\n... and {len(files) - 20} more files"

    await update.message.reply_text(
        message
    )

    summary = result["summary"]

    if summary:
        await send_long_message(
        update,
        summary
        )

async def fix_build(update, context):
    """
    Repair the most recent failed build.
    
    Usage: /fix_build <repair_task_description>
    """
    
    repair_task = " ".join(context.args)
    
    if not repair_task:
        await update.message.reply_text(
            "Usage:\n/fix_build <describe the repair needed>\n\n"
            "Example:\n/fix_build Fix the pytest import error"
        )
        return
    
    project = get_active_project()
    project_name = project["name"]
    
    await update.message.reply_text(
        f"Finding latest failed build for {project_name}..."
    )
    
    try:
        # Find the most recent failed build
        failed_build = await asyncio.to_thread(
            get_latest_failed_build,
            project_name
        )
        
        if not failed_build:
            await update.message.reply_text(
                f"No failed builds found for project: {project_name}"
            )
            return
        
        parent_timestamp = failed_build["timestamp"]
        metadata = failed_build["metadata"]
        validation_output = failed_build["validation_output"]
        generated_dir = failed_build["generated_dir"]
        
        await update.message.reply_text(
            f"Found failed build [{parent_timestamp}]\n"
            f"Original task: {metadata.get('task', 'N/A')}\n"
            f"Error type: {metadata.get('error_type', 'N/A')}\n\n"
            "Loading generated files and constructing repair context..."
        )
        
        # Read generated files as text for context
        generated_files_text = await asyncio.to_thread(
            read_generated_files_as_text,
            generated_dir
        )
        
        # Construct repair context
        repair_context = {
            "parent_timestamp": parent_timestamp,
            "original_task": metadata.get("task"),
            "error_type": metadata.get("error_type"),
            "error_message": metadata.get("error_message"),
            "validation_output": validation_output,
            "generated_files": generated_files_text
        }
        
        await update.message.reply_text(
            "Generating repair build..."
        )
        
        # Call build_project with repair context
        result = await asyncio.to_thread(
            build_project,
            repair_task,
            project,
            repair_context
        )
        
        build_id = result.get("build_id", "unknown")
        files = result["files"]
        status = result.get("status", "unknown")
        error_type = result.get("error_type")
        
        message = (
            f"Repair Build Complete [{build_id}]\n"
            f"Parent: [{parent_timestamp}]\n"
            f"Status: {status}\n\n"
            f"Files Modified: {len(files)}\n\n"
        )
        
        if error_type:
            message += f"⚠️  Validation Error Type: {error_type}\n\n"
        
        message += "\n".join(files[:20])
        
        if len(files) > 20:
            message += f"\n... and {len(files) - 20} more files"
        
        await update.message.reply_text(message)
        
        summary = result.get("summary")
        
        if summary:
            await send_long_message(
                update,
                summary
            )
        
        # Show next steps
        if status == "pending":
            await update.message.reply_text(
                "Use /approve to apply this repair, "
                "or /fix_build again to repair further"
            )
        else:
            await update.message.reply_text(
                "⚠️  Repair has validation errors. "
                "Use /fix_build again to repair further"
            )
    
    except Exception as e:
        await update.message.reply_text(
            f"Fix Build Error:\n{str(e)}"
        )

async def approve(update, context):

    project = get_active_project()
    project_name = project["name"]

    await update.message.reply_text(
        f"Applying build for project: {project_name}..."
    )

    result = await asyncio.to_thread(
        approve_build,
        project
    )

    await update.message.reply_text(
        result
    )

async def pytest_command(update, context):

    await update.message.reply_text(
        "Running pytest..."
    )

    result = await asyncio.to_thread(
        run_pytest
    )

    await send_long_message(
        update,
        result
    )

async def analyze_frames_command(update, context):

    await update.message.reply_text(
        "Analyzing frames..."
    )

    try:

        result = await asyncio.to_thread(
            analyze_frames
        )

    except Exception as e:

        result = (
            "Frame Analysis Error:\n"
            f"{e}"
        )

    await send_long_message(
        update,
        result
    )

async def rollback(update, context):

    await update.message.reply_text(
        "Rolling back..."
    )

    result = await asyncio.to_thread(
        rollback_latest_backup
    )

    if not result["success"]:

        await update.message.reply_text(
            result["message"]
        )
        return

    message = (
        "Rollback successful\n\n"
        f"Source:\n"
        f"{result['backup']}\n\n"
        "Restored Files:\n"
    )

    for f in result["restored"]:

        message += f"✓ {f}\n"

    await send_long_message(
        update,
        message
    )

async def select_project(update, context):
    """Select active project for builds"""
    
    if not context.args:
        
        active = get_active_project()
        all_projects = list_projects()
        
        message = f"Current project: {active['name']}\n\n"
        message += "Available projects:\n"
        for proj in all_projects:
            message += f"  • {proj}\n"
        message += "\nUsage: /select_project <project_name>"
        
        await update.message.reply_text(message)
        return
    
    project_name = context.args[0]
    
    if select_project(project_name):
        await update.message.reply_text(
            f"✓ Switched to project: {project_name}"
        )
    else:
        all_projects = list_projects()
        message = f"Project not found: {project_name}\n\n"
        message += "Available projects:\n"
        for proj in all_projects:
            message += f"  • {proj}\n"
        await update.message.reply_text(message)

def main():
    app = (
    Application.builder()
    .token(BOT_TOKEN)
    .connect_timeout(60)
    .read_timeout(60)
    .write_timeout(60)
    .pool_timeout(60)
    .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("agent", agent))
    app.add_handler(CommandHandler("build", build))
    app.add_handler(CommandHandler("fix_build", fix_build))
    app.add_handler(CommandHandler("select_project", select_project))
    app.add_handler(CommandHandler("gemini", gemini))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("current_state", current_state))
    app.add_handler(CommandHandler("roadmap", roadmap))
    app.add_handler(CommandHandler("review", review))
    app.add_handler(CommandHandler("project_files", project_files))
    app.add_handler(CommandHandler("next_task", next_task))
    app.add_handler(CommandHandler("approve", approve))
    app.add_handler(CommandHandler("pytest", pytest_command))
    app.add_handler(CommandHandler("analyze_frames", analyze_frames_command))
    app.add_handler(CommandHandler("rollback", rollback))

    print("Telegram Agent Started...")

    app.run_polling()


if __name__ == "__main__":
    main()
