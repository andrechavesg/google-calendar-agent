import json
import os
import logging

logger = logging.getLogger(__name__)

CONFIG = {}

def load_config():
    global CONFIG
    try:
        config_path = '/usr/src/app/config.json'
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)

        # Format templates by joining arrays and applying config variables
        CONFIG = raw_config.copy() # Start with raw values

        # Format calendar tool description
        if isinstance(raw_config.get('calendar_tool_description_template'), list):
            desc_template = "\n".join(raw_config['calendar_tool_description_template'])
            CONFIG['calendar_tool_description'] = desc_template.format(**raw_config)
        else:
            CONFIG['calendar_tool_description'] = "Error loading calendar tool description."
            logger.error("calendar_tool_description_template is not a list in config.json")

        # Format agent prompt
        if isinstance(raw_config.get('agent_prompt_template'), list):
            agent_template = "\n".join(raw_config['agent_prompt_template'])
            # Store the raw template; formatting happens in agent.py
            CONFIG['agent_system_prompt_template'] = agent_template
            logger.info(f"Loaded agent prompt template: {agent_template[:100]}...")
        else:
            CONFIG['agent_system_prompt_template'] = "You are a helpful assistant." # Fallback
            logger.error("agent_prompt_template is not a list in config.json")

        # Ensure required keys are present (adjusting for template key)
        required_keys = [
            'initial_message',
            'calendar_tool_description',
            'agent_system_prompt_template', # Check for template key now
            'max_calendar_result_length'
        ]
        for key in required_keys:
             if key not in CONFIG:
                  logger.error(f"Missing required key '{key}' in loaded config.")
                  # Handle missing essential config appropriately
                  if key == 'agent_system_prompt_template': CONFIG[key] = "You are a helpful assistant."
                  if key == 'calendar_tool_description': CONFIG[key] = "Calendar tool."

        logger.info("Configuration loaded successfully.")

    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}")
        CONFIG = {'agent_system_prompt_template': "You are a helpful assistant.", 'calendar_tool_description': "Calendar tool.", 'initial_message': "Error loading config."}
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {config_path}")
        CONFIG = {'agent_system_prompt_template': "You are a helpful assistant.", 'calendar_tool_description': "Calendar tool.", 'initial_message': "Error loading config."}
    except Exception as e:
        logger.exception(f"An unexpected error occurred loading configuration: {e}")
        CONFIG = {'agent_system_prompt_template': "You are a helpful assistant.", 'calendar_tool_description': "Calendar tool.", 'initial_message': "Error loading config."}

# Load config when module is imported
load_config()

# Function to get config values (prevents direct dict access everywhere)
def get_config(key, default=None):
    return CONFIG.get(key, default) 