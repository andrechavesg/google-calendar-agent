from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
import uvicorn
import os
import uuid
import logging
from starlette.websockets import WebSocketState # Import needed for finally block
import datetime # <<< ADDED

# Import config loader
from .config_loader import get_config

# Assuming agent.py is in the same package directory
from .agent import get_agent_executor_with_history, get_session_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
agent_executor = get_agent_executor_with_history()

# Mount static files (HTML, CSS, JS)
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Use Jinja2Templates for rendering index.html potentially (optional here)
templates = Jinja2Templates(directory=static_dir)

# Load initial message from config
# def load_initial_message():
#     try:
#         # Path relative to WORKDIR
#         file_path = '/usr/src/app/initial_message.txt' # Correct path
#         with open(file_path, 'r', encoding='utf-8') as f:
#             return f.read().strip()
#     except Exception as e:
#         logger.error(f"Error loading initial_message.txt: {e}")
#         return "Connected! How can I help?" # Fallback
#
# INITIAL_BOT_MESSAGE = load_initial_message()
INITIAL_BOT_MESSAGE = get_config("initial_message", "Connected! How can I help?")
# Load chat title from config
CHAT_TITLE = get_config("chat_title", "Chat with Calendar")
# Load placeholder from config
INPUT_PLACEHOLDER = get_config("input_placeholder", "Type your message...") # Added

@app.get("/")
async def get(request: Request):
    """Serve the index.html file using Jinja2 to inject configuration."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "initial_message": INITIAL_BOT_MESSAGE,
            "chat_title": CHAT_TITLE,
            "input_placeholder": INPUT_PLACEHOLDER # Pass placeholder to template
        }
    )

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    logger.info(f"WebSocket connection established for session: {session_id}")

    # Ensure session history exists for this session ID
    session_history = get_session_history(session_id)
    logger.info(f"Initial chat history length for session {session_id}: {len(session_history.messages)}")

    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from {session_id}: {data}")
            # Send an initial acknowledgement
            await websocket.send_text(f"Processing your request...")

            # <<< ADD Current Date/Time to input >>>
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            enhanced_input = f"(Current date and time: {now})\nUser query: {data}"
            logger.info(f"Enhanced input for agent: {enhanced_input}")
            # <<< END ADD Current Date/Time >>>

            # Prepare agent configuration for this specific session
            config = {"configurable": {"session_id": session_id}}

            # Run the agent asynchronously
            try:
                logger.info(f"Invoking agent for session {session_id}...")
                # Use enhanced_input
                response = await agent_executor.ainvoke({"input": enhanced_input}, config=config)
                output = response.get("output", "Agent did not produce an output.")
                logger.info(f"Agent output for session {session_id}: {output}")
                await websocket.send_text(output)

            except Exception as e:
                logger.error(f"Agent execution error for session {session_id}: {e}", exc_info=True)
                output = f"An error occurred while processing your request: {str(e)}"
                await websocket.send_text(output)

    except WebSocketDisconnect:
        logger.info(f"Client disconnected for session: {session_id}")
    except Exception as e:
        logger.error(f"WebSocket error for session {session_id}: {e}", exc_info=True)
        try:
            # Attempt to inform the client about the error if possible
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_text(f"An internal server error occurred: {str(e)}")
        except Exception as ws_send_error:
            logger.error(f"Could not send error to client {session_id}: {ws_send_error}")
    finally:
        # Ensure websocket is closed if it's still open
        if websocket.client_state != WebSocketState.DISCONNECTED:
             logger.info(f"Closing WebSocket connection for session {session_id} due to error or disconnect.")
             await websocket.close()
        # Optional: Clean up session history if desired after disconnect
        # if session_id in message_history_store:
        #     del message_history_store[session_id]
        #     logger.info(f"Cleaned up chat history for session: {session_id}")

# Note: The start() function is removed as uvicorn will be run via Docker command
# If you need to run locally without Docker, uncomment and adjust:
def start():
    """Launched with `python -m app.main` for local testing"""
    uvicorn.run("app.main:app", host="0.0.0.0", port=3001, reload=True)

if __name__ == "__main__":
    start()



