import os
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain import hub
from dotenv import load_dotenv
from .tool import GoogleCalendarCLIWrapper
from .config_loader import get_config

load_dotenv()

# --- Load Agent Prompt from File ---
# def load_agent_prompt():
#     try:
#         # Assumes agent_prompt.txt is in the WORKDIR (/usr/src/app)
#         prompt_file_path = '/usr/src/app/agent_prompt.txt' # Updated path
#         with open(prompt_file_path, 'r', encoding='utf-8') as f:
#             return f.read().strip()
#     except FileNotFoundError:
#         print("ERROR: agent_prompt.txt not found at /usr/src/app/. Using basic default prompt.")
#         return "You are a helpful assistant." # Basic fallback
#     except Exception as e:
#          print(f"ERROR loading agent prompt: {e}. Falling back.")
#          return "You are a helpful assistant." # Basic fallback

# AGENT_SYSTEM_PROMPT = get_config("agent_system_prompt", "You are a helpful assistant.")
# --- End Load Agent Prompt ---

# In-memory store for chat histories
message_history_store = {}

def get_session_history(session_id: str) -> ChatMessageHistory:
    if session_id not in message_history_store:
        message_history_store[session_id] = ChatMessageHistory()
    return message_history_store[session_id]

def initialize_agent_executor():
    """Initializes and returns the LangChain agent executor with message history."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "YOUR_OPENAI_API_KEY_HERE":
        raise ValueError("OPENAI_API_KEY not found or not set in .env file.")

    # Initialize the LLM
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=api_key)

    # Initialize tools
    tools = [
        GoogleCalendarCLIWrapper()
        # Hypothetical tools to be added:
        # CalendarAvailabilityTool(),
        # CalendarSchedulerTool(),
    ]

    # Get the ReAct prompt template supporting history
    prompt = hub.pull("hwchase17/react-chat")

    # <<< Format and Modify System Message >>>
    try:
        # Load raw template and config values needed for formatting
        agent_template = get_config("agent_system_prompt_template", "You are a helpful assistant.")
        format_kwargs = {
            "display_timezone_short": get_config("display_timezone_short", "BRT"),
            "display_timezone_utc": get_config("display_timezone_utc", "UTC-3"),
            "internal_timezone_id": get_config("internal_timezone_id", "America/Sao_Paulo"),
            "consultation_duration_minutes": get_config("consultation_duration_minutes", 30)
        }
        # Format the template
        formatted_system_prompt = agent_template.format(**format_kwargs)

        # Find and update the system message within the prompt template messages
        updated = False
        for i, msg_template in enumerate(prompt.messages):
            if msg_template.__class__.__name__ == 'SystemMessagePromptTemplate' and hasattr(msg_template, 'prompt') and hasattr(msg_template.prompt, 'template'):
                 prompt.messages[i].prompt.template = formatted_system_prompt # Use formatted prompt
                 print("INFO: Updated Hub prompt system message from formatted config template.")
                 updated = True
                 break # Assume only one system message
        if not updated:
             print("WARNING: Could not find system message in Hub prompt structure to update. Using default Hub system message.")

    except Exception as e:
         print(f"ERROR formatting/modifying Hub prompt: {e}. Using default Hub system message.")
    # <<< End Format and Modify System Message >>>

    # Create the ReAct agent
    agent = create_react_agent(llm, tools, prompt)

    # Create the agent executor
    base_agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools, 
        verbose=True,
        handle_parsing_errors=True
    )

    # Add message history capabilities
    agent_with_chat_history = RunnableWithMessageHistory(
        base_agent_executor,
        get_session_history,
        input_messages_key="input",
        history_messages_key="chat_history", # Ensure this matches the prompt expectation
    )
    return agent_with_chat_history

# Initialize it once
agent_executor_with_history = initialize_agent_executor()

def get_agent_executor_with_history() -> RunnableWithMessageHistory:
     """Returns the initialized LangChain agent executor with message history."""
     return agent_executor_with_history



