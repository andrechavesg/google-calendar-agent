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
import httpx # <-- Add httpx for API calls

# Import config loader (use absolute import)
from config_loader import get_config

# Assuming agent.py is in the same package directory (use absolute import)
from agent import create_agent_executor_with_history, get_session_history

# Import tools
from tool import GoogleCalendarCLIWrapper, VectorStoreSitemapTool # Changed to VectorStoreSitemapTool

logging.basicConfig(level=logging.DEBUG) # Set to DEBUG
logger = logging.getLogger(__name__)

app = FastAPI()

# Mount static files (HTML, CSS, JS)
# Get directory containing main.py and join with 'static'
static_dir = os.path.join(os.path.dirname(__file__), "static") 
logger.info(f"Calculated static directory: {static_dir}") # Log the path
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Use Jinja2Templates for rendering index.html potentially (optional here)
# Ensure Jinja also uses the correct static directory path
templates = Jinja2Templates(directory=static_dir)

# INITIAL_BOT_MESSAGE = load_initial_message()
INITIAL_BOT_MESSAGE = get_config("initial_message", "Connected! How can I help?")
# Load chat title from config
CHAT_TITLE = get_config("chat_title", "Chat with Calendar")
# Load placeholder from config
INPUT_PLACEHOLDER = get_config("input_placeholder", "Type your message...") # Added

# Load configuration values
QUALIFICATION_PROMPT = get_config("qualification_agent_system_prompt_template", "Error: Qual prompt missing")
SCHEDULING_PROMPT = get_config("scheduling_agent_system_prompt_template", "Error: Sched prompt missing")
QUALIFICATION_API_URL = get_config("qualification_api_url", "")
NOT_QUALIFIED_MESSAGE_TEMPLATE = get_config("not_qualified_message", "Not qualified.")
NOT_QUALIFIED_PDF_URL = get_config("not_qualified_pdf_url", "")

# --- Define Tool Lists ---
# Qualification agent only needs the vector store tool
qualification_tools = [VectorStoreSitemapTool()] # Changed to VectorStoreSitemapTool

# Scheduling agent needs calendar tools
# TODO: Confirm if CalendarAvailabilityTool/CalendarSchedulerTool are separate or part of GoogleCalendarCLIWrapper
scheduling_tools = [GoogleCalendarCLIWrapper()]
# scheduling_tools = [
#     GoogleCalendarCLIWrapper(),
#     CalendarAvailabilityTool(), # If separate
#     CalendarSchedulerTool(),   # If separate
# ]

# Dictionary to store session states (e.g., "qualification", "scheduling")
session_states = {}
# Dictionary to store agent executors per session
session_executors = {}

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

async def initialize_session(session_id: str):
    """Initializes the state and agent executor for a new session."""
    logger.info(f"Initializing session {session_id}...")
    session_states[session_id] = "qualification" # Start in qualification mode
    try:
        logger.info(f"Creating QUALIFICATION agent executor for session {session_id}...")
        agent_executor = create_agent_executor_with_history(
            system_prompt_template_str=QUALIFICATION_PROMPT,
            tools_list=qualification_tools
        )
        session_executors[session_id] = agent_executor
        logger.info(f"Qualification agent executor created successfully for session {session_id}.")
        return agent_executor
    except Exception as init_error:
        logger.error(f"Failed to initialize QUALIFICATION agent executor for session {session_id}: {init_error}", exc_info=True)
        raise # Re-raise the exception to be caught by the websocket handler

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    """Handles WebSocket connections for chat, supporting streaming."""
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for session: {session_id}")

    # Initialize session state and the first (qualification) agent executor
    try:
        agent_executor = await initialize_session(session_id)
    except Exception as init_error:
        # Handle initialization error - inform client and close
        error_message = f"Failed to initialize agent session: {str(init_error)}"
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

            # Get the current agent executor for the session
            # It might change if the state transitions
            current_executor = session_executors.get(session_id)
            if not current_executor:
                 logger.error(f"Agent executor not found for session {session_id}. Reinitializing.")
                 try:
                     # Attempt re-initialization (might default to qualification)
                     current_executor = await initialize_session(session_id)
                 except Exception as reinit_error:
                     error_message = f"Failed to re-initialize agent: {str(reinit_error)}"
                     await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
                     await websocket.close(code=1011)
                     return

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

                # --- Agent Invocation and State Handling --- 
                final_output = "(No output generated)" 
                agent_response_json = None # To store parsed JSON if applicable
                
                try:
                    logger.info(f"Streaming/invoking {session_states.get(session_id, 'unknown')} agent for session {session_id}...")
                    async for chunk in current_executor.astream({"input": enhanced_input}, config=config):
                        if "output" in chunk and isinstance(chunk["output"], str):
                            final_output = chunk["output"]
                            
                    logger.info(f"Agent execution finished for session {session_id}. Raw output length: {len(final_output)}")
                    
                    # --- State-Specific Output Processing ---
                    current_state = session_states.get(session_id, "qualification")
                    
                    if current_state == "qualification":
                        # Log the raw output *before* trying to parse, adding markers for clarity
                        logger.info(f"Processing QUALIFICATION agent output for {session_id}. Raw output:\n>>>\n{final_output}\n<<<" )
                        
                        parsed_json = None
                        try:
                            # Attempt 1: Direct parse
                            parsed_json = json.loads(final_output)
                            logger.info(f"Direct JSON parse successful for {session_id}")
                        except json.JSONDecodeError:
                            logger.warning(f"Direct JSON parse failed for {session_id}. Trying markdown extraction...")
                            try:
                                # Attempt 2: Extract from markdown
                                import re
                                # Added re.IGNORECASE just in case
                                match = re.search(r"```json\s*({.*?})\s*```", final_output, re.DOTALL | re.IGNORECASE)
                                if match:
                                    json_str = match.group(1)
                                    parsed_json = json.loads(json_str) # Assign result here
                                    logger.info(f"Successfully parsed JSON extracted from markdown for {session_id}")
                                else:
                                    logger.warning(f"Markdown extraction failed for {session_id}. No ```json block found.")
                                    # parsed_json remains None
                            except Exception as e_extract: # Catch potential regex or inner parse errors
                                 logger.error(f"Error during markdown extraction/parsing for {session_id}: {e_extract}")
                                 # parsed_json remains None

                        # --- Check results of parsing attempts --- 
                        if parsed_json and "chat_output" in parsed_json:
                            # Ideal Path: Send extracted chat_output
                            await websocket.send_text(json.dumps({"type": "final_answer", "message": parsed_json["chat_output"]}))
                            logger.info(f"Sent 'chat_output' from qualification agent for {session_id}")

                            # Check if qualification is done (only if parsing succeeded and chat_output present)
                            if parsed_json.get("done") is True:
                                logger.info(f"Qualification marked as 'done' for session {session_id}. Calling API.")
                                collected_data = parsed_json.get("collected_data", {})
                                
                                # Call the qualification API
                                async with httpx.AsyncClient() as client:
                                    try:
                                        api_response = await client.post(QUALIFICATION_API_URL, json=collected_data, timeout=30.0) # Added timeout
                                        api_response.raise_for_status() # Raise HTTP errors
                                        qualification_result = api_response.json() # Assuming API returns JSON
                                        logger.info(f"Qualification API call successful for {session_id}. Result: {qualification_result}")
                                        
                                        # --- Check qualification based on API response structure ---
                                        # Old: Assume API returns {'qualified': True/False}
                                        # is_qualified = qualification_result.get("qualified", False)
                                        # New: Check 'classificacao' field is 1
                                        is_qualified = qualification_result.get("classificacao") == 1
                                        # --- End Check ---
                                        
                                        if is_qualified:
                                            logger.info(f"User {session_id} QUALIFIED. Transitioning to scheduling agent.")
                                            session_states[session_id] = "scheduling"
                                            # Create and store the scheduling agent executor
                                            logger.info(f"Creating SCHEDULING agent executor for session {session_id}...")
                                            scheduling_executor = create_agent_executor_with_history(
                                                system_prompt_template_str=SCHEDULING_PROMPT,
                                                tools_list=scheduling_tools
                                            )
                                            session_executors[session_id] = scheduling_executor
                                            logger.info(f"Scheduling agent executor created and stored for session {session_id}.")
                                            # Optionally send a transition message to the client
                                            # await websocket.send_text(json.dumps({"type": "info", "message": "Ótimo! Agora podemos verificar a agenda..."}))
                                            # Let the scheduling agent handle the next interaction naturally
                                            
                                        else:
                                            logger.info(f"User {session_id} NOT QUALIFIED. Sending message and closing.")
                                            # Format the 'not qualified' message
                                            formatted_nq_message = NOT_QUALIFIED_MESSAGE_TEMPLATE.format(not_qualified_pdf_url=NOT_QUALIFIED_PDF_URL)
                                            await websocket.send_text(json.dumps({"type": "final_answer", "message": formatted_nq_message}))
                                            await websocket.close(code=1000) # Normal closure
                                            return # End the handler for this session
                                            
                                    except httpx.RequestError as api_req_err:
                                        logger.error(f"Qualification API request error for session {session_id}: {api_req_err}", exc_info=True)
                                        await websocket.send_text(json.dumps({"type": "error", "message": "Could not reach qualification service."}))
                                    except httpx.HTTPStatusError as api_stat_err:
                                         logger.error(f"Qualification API status error for session {session_id}: {api_stat_err}", exc_info=True)
                                         await websocket.send_text(json.dumps({"type": "error", "message": f"Qualification service error: {api_stat_err.response.status_code}"}))
                                    except json.JSONDecodeError as api_json_err:
                                        logger.error(f"Qualification API response JSON decode error for {session_id}: {api_json_err}", exc_info=True)
                                        await websocket.send_text(json.dumps({"type": "error", "message": "Invalid response from qualification service."}))
                                
                    elif current_state == "scheduling":
                        logger.info(f"Processing SCHEDULING agent output for {session_id}")
                        # Send the complete final answer from scheduling agent
                        await websocket.send_text(json.dumps({"type": "final_answer", "message": final_output}))
                        logger.info(f"Sent final answer from scheduling agent for {session_id}")
                        
                    else: # Should not happen
                         logger.error(f"Invalid session state '{current_state}' for session {session_id}")
                         await websocket.send_text(json.dumps({"type": "error", "message": "Internal state error."}))

                except Exception as agent_error:
                    logger.error(f"Agent execution error for session {session_id}: {agent_error}", exc_info=True)
                    error_message = f"An error occurred during processing: {str(agent_error)}"
                    await websocket.send_text(json.dumps({"type": "error", "message": error_message}))
                
                # Always send end signal regardless of success or error
                await websocket.send_text(json.dumps({"type": "end"}))
                logger.info(f"Sent 'end' signal for {session_id}")

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
        # Clean up session state and executor when client disconnects
        if session_id in session_states:
            del session_states[session_id]
            logger.info(f"Removed state for session {session_id}")
        if session_id in session_executors:
            del session_executors[session_id]
            logger.info(f"Removed agent executor for session {session_id}")
            
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



