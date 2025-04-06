import subprocess
import os
import logging
import json # Added for MCP JSON handling
import uuid # Added for potential request IDs
from typing import Any, Optional
from langchain_core.tools import BaseTool
# from langchain_core.pydantic_v1 import Field, root_validator # Deprecated
from pydantic.v1 import Field, root_validator # Use v1 namespace for compatibility
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI # Needed for summarizer
from langchain_core.prompts import ChatPromptTemplate # Needed for summarizer
from langchain_core.output_parsers import StrOutputParser # Needed for summarizer
from config_loader import get_config # <<< ADDED

load_dotenv()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Load Configurable Values ---

# Remove MAX_CALENDAR_RESULT_LENGTH loading
MAX_CALENDAR_RESULT_LENGTH = get_config("max_calendar_result_length", 2000) # <<< Use config

# Load Tool Description from config
# def load_tool_description():
#     try:
#         # Path relative to WORKDIR
#         description_file_path = '/usr/src/app/calendar_tool_description.txt' # Correct path
#         # No need for abspath as we use a fixed path now
#         with open(description_file_path, 'r', encoding='utf-8') as f:
#             return f.read().strip()
#     except FileNotFoundError:
#         logger.error("calendar_tool_description.txt not found at /usr/src/app/. Falling back.")
#         return "Manages Google Calendar events." # Basic fallback
#     except Exception as e:
#         logger.exception(f"Error loading tool description: {e}. Falling back.")
#         return "Manages Google Calendar events." # Basic fallback
#
# CALENDAR_TOOL_DESCRIPTION = load_tool_description()
CALENDAR_TOOL_DESCRIPTION = get_config("calendar_tool_description", "Calendar tool.") # <<< Use config
# --- End Load Configurable Values ---

# Get the path to the MCP server script from environment variables
# Path is now set directly via ENV in Dockerfile
MCP_SERVER_SCRIPT_PATH = os.getenv("MCP_SERVER_SCRIPT_PATH")
if not MCP_SERVER_SCRIPT_PATH:
    # This should ideally not happen if ENV is set correctly in Dockerfile
     raise ValueError("MCP_SERVER_SCRIPT_PATH environment variable is required but not set.")

# Ensure the script exists (less critical now as it's built into image, but good check)
if not os.path.exists(MCP_SERVER_SCRIPT_PATH):
     logger.warning(f"MCP server script not found at expected path: {MCP_SERVER_SCRIPT_PATH}")
     # Don't raise FileNotFoundError immediately, let subprocess handle it

# --- Summarization Chain Definition ---

# Use a potentially cheaper/faster model for summarization if desired
# Ensure OPENAI_API_KEY is loaded via load_dotenv()
summarizer_llm = ChatOpenAI(model=os.getenv("SUMMARIZER_MODEL", "gpt-3.5-turbo"), temperature=0)
summarizer_prompt = ChatPromptTemplate.from_template(
    "Concisely summarize the following text, focusing on the key information:\n\n{text_to_summarize}\n\nSummary:"
)
summarizer_chain = summarizer_prompt | summarizer_llm | StrOutputParser()

# --- End Summarization Chain Definition ---

class GoogleCalendarSubprocessWrapper(BaseTool):
    """Tool for interacting with the Google Calendar MCP server via subprocess stdio."""
    # Prevent Pydantic v1 from potentially interfering with standard attributes
    __slots__ = ()

    name: str = "google_calendar_tool"
    description: str = CALENDAR_TOOL_DESCRIPTION # Use loaded description
    # No longer need mcp_script_path as instance variable, use module-level constant
    # mcp_script_path: str = MCP_SERVER_SCRIPT_PATH

    def _run(self, command: str, **kwargs: Any) -> str:
        """Use the tool by executing the MCP server and communicating via stdin/stdout."""
        logger.info(f"Received command input for calendar tool: {command}")

        # --- Parse Structured Input ---
        tool_input = None
        tool_name = None
        tool_args = None
        try:
            if isinstance(command, dict):
                # Agent might pass the dictionary directly
                logger.info("Tool input received as dictionary.")
                tool_input = command
            elif isinstance(command, str):
                # Agent passes a string, try parsing as JSON
                logger.info("Tool input received as string, attempting JSON parse.")
                try:
                    # Clean the string: strip whitespace and potential markdown backticks
                    cleaned_command = command.strip()
                    if cleaned_command.startswith("```json\n"):
                        cleaned_command = cleaned_command[len("```json\n"):]
                    if cleaned_command.startswith("```"):
                         cleaned_command = cleaned_command[3:]
                    if cleaned_command.endswith("\n```"):
                         cleaned_command = cleaned_command[:-len("\n```")]
                    if cleaned_command.endswith("```"):
                        cleaned_command = cleaned_command[:-3]
                    cleaned_command = cleaned_command.strip() # Strip again after removing backticks

                    tool_input = json.loads(cleaned_command)
                except json.JSONDecodeError:
                    # Handle potential double escaping from some agents
                    logger.warning(f"Initial JSON parse failed for cleaned string: {cleaned_command}. Trying to fix escaping.")
                    try:
                        fixed_command = cleaned_command.replace('\"', '"') # Replace escaped quotes
                        tool_input = json.loads(fixed_command)
                    except Exception as e_fix:
                        logger.error(f"Failed to parse tool input string even after fixing escapes: {command} (cleaned: {cleaned_command}) - Error: {e_fix}")
                        return "Error: Tool input string is not valid JSON, even after attempting to fix escaping and cleaning."
            else:
                 raise TypeError(f"Unexpected command input type: {type(command)}")

            # Validate the parsed/received dictionary
            tool_name = tool_input.get("name")
            tool_args = tool_input.get("arguments", {})

            if not tool_name or not isinstance(tool_args, dict):
                raise ValueError("Input must resolve to a dictionary containing 'name' (string) and 'arguments' (object).")

            logger.info(f"Parsed MCP Tool Name: {tool_name}")
            logger.info(f"Parsed MCP Arguments (original): {tool_args}")

            # --- Inject Default Calendar ID if needed --- Start
            if not tool_args.get("calendarId"):
                # Check if the tool actually requires/uses calendarId (optional optimization)
                # For simplicity, we'll try to inject it for common calendar operations
                relevant_tools = ['list-events', 'create-event', 'search-events', 'update-event', 'delete-event']
                if tool_name in relevant_tools:
                    default_id = get_config('default_calendar_id')
                    if default_id:
                        tool_args['calendarId'] = default_id
                        logger.info(f"Injected default_calendar_id: {default_id}")
                    else:
                        logger.warning(f"Tool '{tool_name}' might need calendarId, but none provided and no default_calendar_id found in config.")
            # --- Inject Default Calendar ID if needed --- End

        except (json.JSONDecodeError, TypeError, ValueError) as e:
             logger.error(f"Invalid tool input format: {command} - {e}")
             return f"Error: Invalid tool input format. {e}"
        # --- End Parse Input ---

        # Use the module-level MCP_SERVER_SCRIPT_PATH
        logger.info(f"Executing MCP server: node {MCP_SERVER_SCRIPT_PATH}")

        # --- Construct the MCP Request ---
        request_id = str(uuid.uuid4())
        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",  # CORRECT method name found in SDK source
            "id": request_id,
            "params": {           # Structure PARAMS to match CallToolRequestSchema directly
                "name": tool_name,
                "arguments": tool_args
            }
        }
        mcp_request_json = json.dumps(mcp_request) + "\n"
        logger.info(f"Sending MCP Request (stdin): {mcp_request_json.strip()}")
        # --- End MCP Request Construction ---

        # (Subprocess execution logic requires manual stream handling)
        process = None # Define process outside try block for finally clause
        try:
            process = subprocess.Popen(
                ['node', MCP_SERVER_SCRIPT_PATH], # Use module-level constant
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1 # Line buffering
            )

            # Write request to stdin
            try:
                process.stdin.write(mcp_request_json)
                process.stdin.flush() # Ensure data is sent
                process.stdin.close() # Signal end of request
                logger.info("MCP request sent to stdin and stream closed.")
            except BrokenPipeError:
                logger.error("Failed to write to MCP server stdin. Process likely terminated early.")
                # Capture any initial stderr
                stderr_data = process.stderr.read()
                logger.error(f"MCP Server initial stderr: {stderr_data}")
                return f"Error: Could not send request to calendar server process. Stderr: {stderr_data}"
            except Exception as e_write:
                 logger.exception("An unexpected error occurred writing to stdin.")
                 return f"Error writing to calendar server: {e_write}"

            # Read response from stdout, with timeout
            response_lines = []
            stderr_lines = []
            stdout_complete_json = None
            try:
                # We need a way to read with timeout without communicate()
                # Using select or threading is complex. A simpler approach for now
                # is to read line by line but implement a manual timeout mechanism.
                # Or, we can try reading stdout first before checking return code/stderr.
                # Reading stderr in a separate thread might be necessary to avoid deadlocks.

                # Read stderr first (non-blocking or short timeout) - simpler but might miss things
                # stderr_data = process.stderr.read() # This might block!
                # Better: Use select or threads. Simpler alternative: communicate with tiny timeout
                try:
                    _, stderr_data_initial = process.communicate(timeout=0.1) # Try getting quick stderr
                    stderr_lines.append(stderr_data_initial)
                    logger.info(f"MCP Server initial stderr (communicate):\n{stderr_data_initial}")
                except subprocess.TimeoutExpired:
                    logger.info("No immediate stderr from MCP server.")
                except Exception as e_comm_stderr:
                     logger.error(f"Error during initial stderr communicate: {e_comm_stderr}")

                logger.info("Attempting to read stdout...")
                # Now read stdout line-by-line - THIS CAN STILL HANG if server doesn't write
                # A select-based approach or threading is more robust for simultaneous reads.
                for line in process.stdout:
                    line = line.strip()
                    if not line: continue
                    logger.info(f"MCP Server stdout line: {line}")
                    response_lines.append(line)
                    # Check if we received a complete JSON object (simple check)
                    if line.startswith('{') and line.endswith('}'):
                        stdout_complete_json = line
                        break # Assume one JSON response per request for now

                # Read any remaining stderr after stdout is done (or if stdout loop finished)
                stderr_data_remaining = process.stderr.read()
                if stderr_data_remaining:
                     stderr_lines.append(stderr_data_remaining)
                     logger.info(f"MCP Server remaining stderr:\n{stderr_data_remaining}")

                stdout_data = "\n".join(response_lines)
                stderr_data = "\n".join(filter(None, stderr_lines))

            except Exception as e_read:
                logger.exception("Error reading from MCP server streams.")
                stderr_data = "".join(stderr_lines) + process.stderr.read() # Try to get final stderr
                return f"Error reading from calendar server: {e_read}. Stderr: {stderr_data}"

            # --- Process the MCP Response --- (using stdout_complete_json or stdout_data)
            try:
                # Prioritize the detected complete JSON object
                json_to_parse = stdout_complete_json
                if not json_to_parse:
                    # Fallback: Maybe the whole output is the JSON
                    json_to_parse = stdout_data.strip()
                    if not (json_to_parse.startswith('{') and json_to_parse.endswith('}')):
                         json_to_parse = None # Not a likely JSON object

                if json_to_parse:
                    mcp_response = json.loads(json_to_parse)
                    logger.info(f"Parsed MCP Response: {mcp_response}")

                    if "error" in mcp_response:
                        error_info = mcp_response["error"]
                        return f"Error from calendar server: {error_info.get('message', 'Unknown error')} (Code: {error_info.get('code', 'N/A')})"
                    elif "result" in mcp_response:
                        result_content = mcp_response["result"].get("content", [])
                        result_text = ""
                        if isinstance(result_content, list) and len(result_content) > 0 and "text" in result_content[0]:
                            result_text = result_content[0]["text"]
                        else:
                            result_text = json.dumps(mcp_response["result"])

                        # <<< Summarize long results INSTEAD of truncating >>>
                        if len(result_text) > MAX_CALENDAR_RESULT_LENGTH:
                             logger.warning(f"Calendar tool result length ({len(result_text)}) exceeds threshold ({MAX_CALENDAR_RESULT_LENGTH}). Summarizing...")
                             # Directly invoke the summarizer chain
                             try:
                                 summary = summarizer_chain.invoke({"text_to_summarize": result_text})
                                 return f"(Summarized due to length): {summary}"
                             except Exception as e_summary:
                                 logger.exception("Error during summarization chain invocation.")
                                 return f"Error summarizing result: {e_summary}"
                        else:
                             # Return the full text if below threshold
                             return result_text
                        # <<< End Summarization Logic >>>
                    else:
                        return "Received unexpected response structure from calendar server."
                elif stderr_data:
                    return f"Calendar server finished with no JSON result, but reported errors: {stderr_data.strip()}"
                elif stdout_data:
                     # Might be non-JSON logs or messages
                     return f"Received non-JSON response from calendar server: {stdout_data.strip()}"
                else:
                     return "Calendar server finished with no output."

            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON response from MCP server stdout: {stdout_data}")
                return f"Error: Could not parse response from calendar server. Raw output:\n{stdout_data}"
            # --- End MCP Response Processing ---

        except subprocess.TimeoutExpired: # This specific exception might not be hit with manual reads
            logger.error("Subprocess operation timed out (manual handling). This shouldn't usually happen here.")
            # Ensure process is killed if it exists and is running
            if process and process.poll() is None:
                 process.kill()
                 stdout_data, stderr_data = process.communicate() # Capture final output after kill
                 logger.error(f"Final stdout after kill: {stdout_data}")
                 logger.error(f"Final stderr after kill: {stderr_data}")
            return "Error: The request to the calendar server timed out."
        except FileNotFoundError:
            logger.error(f"Could not execute MCP server. 'node' command not found or script path incorrect: {MCP_SERVER_SCRIPT_PATH}")
            return "Error: Could not start the calendar server subprocess. Check environment."
        except Exception as e:
            logger.exception("An unexpected error occurred during subprocess communication.")
            # Ensure process is killed if it exists and is running
            if process and process.poll() is None:
                 process.kill()
            return f"An unexpected error occurred: {e}"
        finally:
             # Ensure the process is cleaned up if it's still running
             if process and process.poll() is None:
                 logger.warning("MCP process still running after handling, attempting to terminate.")
                 process.terminate() # Ask nicely first
                 try:
                     process.wait(timeout=1) # Wait briefly
                 except subprocess.TimeoutExpired:
                     logger.warning("MCP process did not terminate gracefully, killing.")
                     process.kill() # Force kill

    async def _arun(self, command: str, **kwargs: Any) -> str:
        logger.info(f"Async received command input for calendar tool: {command}")
        # ... (rest of the async input parsing - should mirror _run)
        # --- Assume input parsing mirrored from _run results in tool_name, tool_args --- START
        tool_input = None
        tool_name = None
        tool_args = None
        try:
            # Mirror the parsing logic from _run diligently
            if isinstance(command, dict):
                tool_input = command
            elif isinstance(command, str):
                cleaned_command = command.strip()
                if cleaned_command.startswith("```json\n"):
                    cleaned_command = cleaned_command[len("```json\n"):]
                if cleaned_command.startswith("```"):
                     cleaned_command = cleaned_command[3:]
                if cleaned_command.endswith("\n```"):
                     cleaned_command = cleaned_command[:-len("\n```")]
                if cleaned_command.endswith("```"):
                    cleaned_command = cleaned_command[:-3]
                cleaned_command = cleaned_command.strip()

                try:
                    tool_input = json.loads(cleaned_command)
                except json.JSONDecodeError:
                    logger.warning(f"Async initial JSON parse failed. Trying to fix escaping.")
                    try:
                        fixed_command = cleaned_command.replace('\"', '"')
                        tool_input = json.loads(fixed_command)
                    except Exception as e_fix:
                        logger.error(f"Async failed to parse tool input string: {command} - Error: {e_fix}")
                        return "Error: Async tool input string is not valid JSON."
            else:
                 raise TypeError(f"Async unexpected command input type: {type(command)}")

            tool_name = tool_input.get("name")
            tool_args = tool_input.get("arguments", {})

            if not tool_name or not isinstance(tool_args, dict):
                raise ValueError("Async input must resolve to a dictionary containing 'name' and 'arguments'.")

            logger.info(f"Async Parsed MCP Tool Name: {tool_name}")
            logger.info(f"Async Parsed MCP Arguments (original): {tool_args}")

            # --- Inject Default Calendar ID if needed (Mirror _run logic) --- Start
            if not tool_args.get("calendarId"):
                relevant_tools = ['list-events', 'create-event', 'search-events', 'update-event', 'delete-event']
                if tool_name in relevant_tools:
                    default_id = get_config('default_calendar_id')
                    if default_id:
                        tool_args['calendarId'] = default_id
                        logger.info(f"Async Injected default_calendar_id: {default_id}")
                    else:
                        logger.warning(f"Async Tool '{tool_name}' might need calendarId, but none provided and no default_calendar_id found.")
            # --- Inject Default Calendar ID if needed (Mirror _run logic) --- End

        except (json.JSONDecodeError, TypeError, ValueError) as e:
             logger.error(f"Async invalid tool input format: {command} - {e}")
             return f"Error: Async invalid tool input format. {e}"
        # --- Assume input parsing mirrored from _run results in tool_name, tool_args --- END

        logger.info(f"Async Executing MCP server: node {MCP_SERVER_SCRIPT_PATH}")

        # Construct MCP Request (mirror _run)
        request_id = str(uuid.uuid4())
        mcp_request = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "id": request_id,
            "params": {
                "name": tool_name,
                "arguments": tool_args
            }
        }
        mcp_request_json = json.dumps(mcp_request) + "\n"
        logger.info(f"Async Sending MCP Request (stdin): {mcp_request_json.strip()}")

        # (Subprocess execution logic requires manual stream handling)
        process = None # Define process outside try block for finally clause
        try:
            process = subprocess.Popen(
                ['node', MCP_SERVER_SCRIPT_PATH], # Use module-level constant
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                bufsize=1 # Line buffering
            )

            # Write request to stdin
            try:
                process.stdin.write(mcp_request_json)
                process.stdin.flush() # Ensure data is sent
                process.stdin.close() # Signal end of request
                logger.info("MCP request sent to stdin and stream closed.")
            except BrokenPipeError:
                logger.error("Failed to write to MCP server stdin. Process likely terminated early.")
                # Capture any initial stderr
                stderr_data = process.stderr.read()
                logger.error(f"MCP Server initial stderr: {stderr_data}")
                return f"Error: Could not send request to calendar server process. Stderr: {stderr_data}"
            except Exception as e_write:
                 logger.exception("An unexpected error occurred writing to stdin.")
                 return f"Error writing to calendar server: {e_write}"

            # Read response from stdout, with timeout
            response_lines = []
            stderr_lines = []
            stdout_complete_json = None
            try:
                # We need a way to read with timeout without communicate()
                # Using select or threading is complex. A simpler approach for now
                # is to read line by line but implement a manual timeout mechanism.
                # Or, we can try reading stdout first before checking return code/stderr.
                # Reading stderr in a separate thread might be necessary to avoid deadlocks.

                # Read stderr first (non-blocking or short timeout) - simpler but might miss things
                # stderr_data = process.stderr.read() # This might block!
                # Better: Use select or threads. Simpler alternative: communicate with tiny timeout
                try:
                    _, stderr_data_initial = process.communicate(timeout=0.1) # Try getting quick stderr
                    stderr_lines.append(stderr_data_initial)
                    logger.info(f"MCP Server initial stderr (communicate):\n{stderr_data_initial}")
                except subprocess.TimeoutExpired:
                    logger.info("No immediate stderr from MCP server.")
                except Exception as e_comm_stderr:
                     logger.error(f"Error during initial stderr communicate: {e_comm_stderr}")

                logger.info("Attempting to read stdout...")
                # Now read stdout line-by-line - THIS CAN STILL HANG if server doesn't write
                # A select-based approach or threading is more robust for simultaneous reads.
                for line in process.stdout:
                    line = line.strip()
                    if not line: continue
                    logger.info(f"MCP Server stdout line: {line}")
                    response_lines.append(line)
                    # Check if we received a complete JSON object (simple check)
                    if line.startswith('{') and line.endswith('}'):
                        stdout_complete_json = line
                        break # Assume one JSON response per request for now

                # Read any remaining stderr after stdout is done (or if stdout loop finished)
                stderr_data_remaining = process.stderr.read()
                if stderr_data_remaining:
                     stderr_lines.append(stderr_data_remaining)
                     logger.info(f"MCP Server remaining stderr:\n{stderr_data_remaining}")

                stdout_data = "\n".join(response_lines)
                stderr_data = "\n".join(filter(None, stderr_lines))

            except Exception as e_read:
                logger.exception("Error reading from MCP server streams.")
                stderr_data = "".join(stderr_lines) + process.stderr.read() # Try to get final stderr
                return f"Error reading from calendar server: {e_read}. Stderr: {stderr_data}"

            # --- Process the MCP Response --- (using stdout_complete_json or stdout_data)
            try:
                # Prioritize the detected complete JSON object
                json_to_parse = stdout_complete_json
                if not json_to_parse:
                    # Fallback: Maybe the whole output is the JSON
                    json_to_parse = stdout_data.strip()
                    if not (json_to_parse.startswith('{') and json_to_parse.endswith('}')):
                         json_to_parse = None # Not a likely JSON object

                if json_to_parse:
                    mcp_response = json.loads(json_to_parse)
                    logger.info(f"Parsed MCP Response: {mcp_response}")

                    if "error" in mcp_response:
                        error_info = mcp_response["error"]
                        return f"Error from calendar server: {error_info.get('message', 'Unknown error')} (Code: {error_info.get('code', 'N/A')})"
                    elif "result" in mcp_response:
                        result_content = mcp_response["result"].get("content", [])
                        result_text = ""
                        if isinstance(result_content, list) and len(result_content) > 0 and "text" in result_content[0]:
                            result_text = result_content[0]["text"]
                        else:
                            result_text = json.dumps(mcp_response["result"])

                        # <<< Summarize long results INSTEAD of truncating >>>
                        if len(result_text) > MAX_CALENDAR_RESULT_LENGTH:
                             logger.warning(f"Calendar tool result length ({len(result_text)}) exceeds threshold ({MAX_CALENDAR_RESULT_LENGTH}). Summarizing...")
                             # Directly invoke the summarizer chain
                             try:
                                 summary = summarizer_chain.invoke({"text_to_summarize": result_text})
                                 return f"(Summarized due to length): {summary}"
                             except Exception as e_summary:
                                 logger.exception("Error during summarization chain invocation.")
                                 return f"Error summarizing result: {e_summary}"
                        else:
                             # Return the full text if below threshold
                             return result_text
                        # <<< End Summarization Logic >>>
                    else:
                        return "Received unexpected response structure from calendar server."
                elif stderr_data:
                    return f"Calendar server finished with no JSON result, but reported errors: {stderr_data.strip()}"
                elif stdout_data:
                     # Might be non-JSON logs or messages
                     return f"Received non-JSON response from calendar server: {stdout_data.strip()}"
                else:
                     return "Calendar server finished with no output."

            except json.JSONDecodeError:
                logger.error(f"Failed to decode JSON response from MCP server stdout: {stdout_data}")
                return f"Error: Could not parse response from calendar server. Raw output:\n{stdout_data}"
            # --- End MCP Response Processing ---

        except subprocess.TimeoutExpired: # This specific exception might not be hit with manual reads
            logger.error("Subprocess operation timed out (manual handling). This shouldn't usually happen here.")
            # Ensure process is killed if it exists and is running
            if process and process.poll() is None:
                 process.kill()
                 stdout_data, stderr_data = process.communicate() # Capture final output after kill
                 logger.error(f"Final stdout after kill: {stdout_data}")
                 logger.error(f"Final stderr after kill: {stderr_data}")
            return "Error: The request to the calendar server timed out."
        except FileNotFoundError:
            logger.error(f"Could not execute MCP server. 'node' command not found or script path incorrect: {MCP_SERVER_SCRIPT_PATH}")
            return "Error: Could not start the calendar server subprocess. Check environment."
        except Exception as e:
            logger.exception("An unexpected error occurred during subprocess communication.")
            # Ensure process is killed if it exists and is running
            if process and process.poll() is None:
                 process.kill()
            return f"An unexpected error occurred: {e}"
        finally:
             # Ensure the process is cleaned up if it's still running
             if process and process.poll() is None:
                 logger.warning("MCP process still running after handling, attempting to terminate.")
                 process.terminate() # Ask nicely first
                 try:
                     process.wait(timeout=1) # Wait briefly
                 except subprocess.TimeoutExpired:
                     logger.warning("MCP process did not terminate gracefully, killing.")
                     process.kill() # Force kill

# Rename the class reference to maintain compatibility with agent.py
GoogleCalendarCLIWrapper = GoogleCalendarSubprocessWrapper



