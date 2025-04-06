import os
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_react_agent
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain import hub
from dotenv import load_dotenv
from .tool import GoogleCalendarCLIWrapper

load_dotenv()

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

    # Initialize the LLM (use a newer model if available like gpt-4o)
    llm = ChatOpenAI(model="gpt-4o", temperature=0.2, openai_api_key=api_key)

    # Initialize the custom tool
    tools = [GoogleCalendarCLIWrapper()]

    # Get the ReAct prompt template supporting history
    prompt = hub.pull("hwchase17/react-chat") # Standard react chat
    # prompt = hub.pull("hwchase17/react-agent-executor") # Often works well

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



