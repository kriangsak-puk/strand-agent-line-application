import logging
import os

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.webhook import WebhookParser
from linebot.v3.webhooks import MessageEvent, TextMessageContent, UserSource
from starlette.concurrency import run_in_threadpool

from adapter.line_client import mark_as_read, push_text, reply_text, show_loading_animation
from agent.respond import respond_agentcore, respond_local

load_dotenv()

logger = logging.getLogger(__name__)

app = FastAPI()
_parser = WebhookParser(os.environ["LINE_CHANNEL_SECRET"])


def _respond(user_id: str, text: str) -> str:
    # AGENT_BACKEND=local     -> in-process strands.Agent
    # AGENT_BACKEND=agentcore -> boto3 invoke_agent_runtime against a
    #                            deployed AgentCore Runtime
    if os.environ.get("AGENT_BACKEND", "local") == "agentcore":
        return respond_agentcore(user_id, text)
    return respond_local(user_id, text)


@app.post("/callback")
async def callback(request: Request, background_tasks: BackgroundTasks) -> str:
    signature = request.headers.get("X-Line-Signature", "")
    body = (await request.body()).decode("utf-8")

    try:
        events = _parser.parse(body, signature)
    except InvalidSignatureError:
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if isinstance(event, MessageEvent) and isinstance(event.message, TextMessageContent):
            background_tasks.add_task(_handle_message, event)

    # Ack immediately; FastAPI runs the tasks above only after this
    # response has been sent, so the agent turn (LLM + web search)
    # never delays LINE's webhook response (see PLAN.md §5).
    return "OK"


async def _handle_message(event: MessageEvent) -> None:
    user_id = event.source.user_id if isinstance(event.source, UserSource) else "anonymous"
    text = event.message.text

    if event.message.mark_as_read_token:
        try:
            await mark_as_read(event.message.mark_as_read_token)
        except Exception:
            logger.exception("mark-as-read failed")

    if user_id != "anonymous":
        try:
            await show_loading_animation(user_id)
        except Exception:
            logger.exception("show-loading-animation failed")

    try:
        reply = await run_in_threadpool(_respond, user_id, text)
    except Exception:
        logger.exception("agent turn failed")
        reply = "Sorry, something went wrong answering that."

    try:
        await reply_text(event.reply_token, reply)
    except Exception:
        logger.exception("reply token expired or reply failed, falling back to push")
        if user_id != "anonymous":
            await push_text(user_id, reply)
