import asyncio
from urllib import response
from claude_runner import ask_claude, build_with_claude
from gemini_runner import ask_gemini
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from pathlib import Path
from config import BOT_TOKEN, PROJECT_DIR

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

    path = Path(PROJECT_DIR) / relative_path

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
    app.add_handler(CommandHandler("gemini", gemini))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("current_state", current_state))
    app.add_handler(CommandHandler("roadmap", roadmap))
    app.add_handler(CommandHandler("review", review))

    print("Telegram Agent Started...")

    app.run_polling()


if __name__ == "__main__":
    main()
