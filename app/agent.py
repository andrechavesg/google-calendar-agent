import os
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from dotenv import load_dotenv
from tool import GoogleCalendarCLIWrapper, VectorStoreSitemapTool
from config_loader import get_config
from langchain.tools.render import render_text_description

load_dotenv()

# --- Removed loading agent prompt from file ---

# --- Removed global AGENT_SYSTEM_PROMPT ---

# In-memory store for chat histories
message_history_store = {}

def get_session_history(session_id: str) -> ChatMessageHistory:
    if session_id not in message_history_store:
        message_history_store[session_id] = ChatMessageHistory()
    return message_history_store[session_id]

# Renamed function and added parameters: system_prompt_template_str, tools_list
def create_agent_executor_with_history(system_prompt_template_str: str, tools_list: list):
    """Creates and returns a LangChain agent executor with message history, configured with the provided system prompt and tools."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or api_key == "YOUR_OPENAI_API_KEY_HERE":
        raise ValueError("OPENAI_API_KEY not found or not set in .env file.")

    # Initialize the LLM
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=api_key)

    # --- Tools are now passed in via tools_list parameter ---
    # tools_list = [
    #     GoogleCalendarCLIWrapper()
    # ]

    # --- System Prompt is now passed in via system_prompt_template_str parameter ---
    # system_prompt_template_str = get_config("agent_system_prompt_template", "You are a helpful assistant.")
    # print(f"INFO: Using system prompt template from config.")

    # --- Create ChatPromptTemplate directly using the passed-in prompt string ---
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt_template_str),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        ("ai", "{agent_scratchpad}")
    ])

    # --- Add required variables for ReAct prompt ---
    # The ReAct prompt needs the tools and tool_names to format the prompt correctly
    prompt = prompt.partial(
        tools=render_text_description(tools_list),
        tool_names=", ".join([t.name for t in tools_list]),
    )

    # Create the ReAct agent
    agent = create_react_agent(llm, tools_list, prompt)

    # Create the agent executor
    base_agent_executor = AgentExecutor(
        agent=agent, 
        tools=tools_list, 
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

# --- Removed global agent_executor_with_history initialization ---
# agent_executor_with_history = initialize_agent_executor()

# --- Removed get_agent_executor_with_history() function ---
# def get_agent_executor_with_history() -> RunnableWithMessageHistory:
#      """Returns the initialized LangChain agent executor with message history."""
#      return agent_executor_with_history



