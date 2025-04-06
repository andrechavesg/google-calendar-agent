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
import json # Add json import
import asyncio # Add asyncio import
from langchain_openai import ChatOpenAI

# Import config loader (use absolute import)
from config_loader import get_config

# Assuming agent.py is in the same package directory (use absolute import)
from agent import get_agent_executor_with_history, get_session_history

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()
# agent_executor = get_agent_executor_with_history() # Comment out global initialization

# Mount static files (HTML, CSS, JS)
# Get directory containing main.py and join with 'static'
static_dir = os.path.join(os.path.dirname(__file__), "static") 
logger.info(f"Calculated static directory: {static_dir}") # Log the path
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Use Jinja2Templates for rendering index.html potentially (optional here)
# Ensure Jinja also uses the correct static directory path
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
    """Handles WebSocket connections for chat, supporting streaming."""
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for session: {session_id}")

    # Initialize agent executor lazily for this connection
    try:
        logger.info(f"Initializing agent executor for session {session_id}...")
        agent_executor = get_agent_executor_with_history() 
        logger.info(f"Agent executor initialized successfully for session {session_id}.")
    except Exception as init_error:
        logger.error(f"Failed to initialize agent executor for session {session_id}: {init_error}", exc_info=True)
        error_message = f"Failed to initialize agent: {str(init_error)}"
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
            await websocket.close(code=1011) # Internal Error
        except Exception as send_err:
            logger.error(f"Could not send agent initialization error to client {session_id}: {send_err}")
        return # Stop processing if agent fails to initialize

    try: # Top-level try block now starts AFTER agent initialization
        # Ensure session history exists
        get_session_history(session_id)
        logger.info(f"Session history check complete for {session_id}")

        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from {session_id}: {data}")

            try: # Inner try for processing a single message
                # <<< ADD Current Date/Time to input >>>
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
                enhanced_input = f"(Current date and time: {now})\nUser query: {data}"
                logger.info(f"Enhanced input for agent {session_id}: {enhanced_input}")
                # <<< END ADD Current Date/Time >>>

                # Prepare agent configuration for this specific session
                config = {"configurable": {"session_id": session_id}}
                logger.info(f"Prepared config for agent {session_id}")

                # Signal start of response generation
                await websocket.send_text(json.dumps({"type": "start"}))
                logger.info(f"Sent 'start' signal for {session_id}")

                # Stream the agent's response
                full_response = ""
                agent_timed_out = False # Flag to track timeout
                try:
                    logger.info(f"Starting agent stream for session {session_id}...")
                    # Wrap the stream iteration with a timeout
                    stream_iterator = agent_executor.astream({"input": enhanced_input}, config=config)
                    while True:
                        try:
                            # Wait for the next chunk with a timeout
                            chunk = await asyncio.wait_for(stream_iterator.__anext__(), timeout=60.0) 
                            # Check for final answer tokens
                            if "output" in chunk and isinstance(chunk["output"], str):
                                token = chunk["output"]
                                if token:
                                    await websocket.send_text(json.dumps({"type": "stream", "token": token}))
                                    full_response += token
                            # Optional: Log other chunk types for debugging if needed
                        except StopAsyncIteration:
                            # Stream finished normally
                            logger.info(f"Agent stream finished normally for session {session_id}.")
                            break # Exit the while loop
                        except asyncio.TimeoutError:
                            agent_timed_out = True
                            logger.error(f"Agent stream timed out after 60 seconds for session {session_id}.")
                            error_message = "The request timed out while waiting for the agent's response."
                            await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
                            break # Exit the while loop on timeout

                    if not agent_timed_out:
                        logger.info(f"Agent stream finished for session {session_id}. Full response length: {len(full_response)}")
                        await websocket.send_text(json.dumps({"type": "end"}))
                        logger.info(f"Sent 'end' signal for {session_id}")
                    else: 
                        # If it timed out, we already sent error, just send end
                         await websocket.send_text(json.dumps({"type": "end"})) 
                         logger.info(f"Sent 'end' signal for {session_id} after timeout.")


                except Exception as stream_error:
                    # Catch errors other than TimeoutError during streaming setup or processing
                    logger.error(f"Agent streaming error for session {session_id}: {stream_error}", exc_info=True)
                    error_message = f"An error occurred during processing: {str(stream_error)}"
                    await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
                    await websocket.send_text(json.dumps({"type": "end"})) # Ensure state resets
                    logger.info(f"Sent 'error' and 'end' signals for {session_id} after stream error.")

            except Exception as processing_error:
                # Catch errors during message processing BEFORE streaming starts
                logger.error(f"Error processing message for session {session_id}: {processing_error}", exc_info=True)
                error_message = f"Failed to process message: {str(processing_error)}"
                # Try to send error to client, even if 'start' wasn't sent
                try:
                    await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
                    await websocket.send_text(json.dumps({"type": "end"})) # Ensure state resets
                    logger.info(f"Sent 'error' and 'end' signals for {session_id} after processing error.")
                except Exception as send_err:
                    logger.error(f"Could not send processing error to client {session_id}: {send_err}")

    except WebSocketDisconnect:
        logger.info(f"Client disconnected for session: {session_id}")
    except Exception as e:
        # Catch errors happening outside the main message loop (e.g., during accept, get_session_history)
        logger.error(f"WebSocket error for session {session_id} (outside main loop): {e}", exc_info=True)
        try:
            # Attempt to inform the client about the error if possible
            if websocket.client_state == WebSocketState.CONNECTED:
                 error_message = f"An internal server error occurred: {str(e)}"
                 await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
                 # Optionally close here if it's a fatal setup error
                 # await websocket.close(code=1011) # Internal Error
        except Exception as ws_send_error:
            logger.error(f"Could not send initial error to client {session_id}: {ws_send_error}")
    finally:
        # Ensure websocket is closed if it's still open
        if websocket.client_state != WebSocketState.DISCONNECTED:
             logger.info(f"Closing WebSocket connection for session {session_id} in finally block.")
             await websocket.close()

# Note: The start() function is removed as uvicorn will be run via Docker command
# If you need to run locally without Docker, uncomment and adjust:
def start():
    """Launched with `python -m app.main` for local testing"""
    uvicorn.run("app.main:app", host="0.0.0.0", port=3001, reload=True)

if __name__ == "__main__":
    start()



