import json
import os
import logging
import string # Import string for custom formatter

logger = logging.getLogger(__name__)

CONFIG = {}

# Custom Formatter to ignore missing keys
class SafeFormatter(string.Formatter):
    def get_value(self, key, args, kwargs):
        if isinstance(key, str):
            try:
                return kwargs[key]
            except KeyError:
                return f'{{{key}}}' # Return the placeholder itself if key not found
        else:
            return super().get_value(key, args, kwargs)

safe_formatter = SafeFormatter()

def load_config():
    global CONFIG
    try:
        config_path = '/usr/src/app/config.json'
        with open(config_path, 'r', encoding='utf-8') as f:
            raw_config = json.load(f)

        # Start with raw values
        CONFIG = raw_config.copy()

        # Format calendar tool description safely
        if isinstance(raw_config.get('calendar_tool_description_template'), list):
            desc_template_list = raw_config['calendar_tool_description_template']
            formatted_desc_list = [
                safe_formatter.format(line, **raw_config) for line in desc_template_list
            ]
            CONFIG['calendar_tool_description'] = "\n".join(formatted_desc_list)
        else:
            CONFIG['calendar_tool_description'] = "Error loading calendar tool description."
            logger.error("calendar_tool_description_template is not a list in config.json")

        # Format agent prompt template safely
        if isinstance(raw_config.get('agent_prompt_template'), list):
            agent_template_list = raw_config['agent_prompt_template']
            # Format each line using safe_formatter and the entire raw_config
            formatted_agent_list = [
                safe_formatter.format(line, **raw_config) for line in agent_template_list
            ]
            # Store the list of formatted strings
            CONFIG['agent_system_prompt_template_list'] = formatted_agent_list
            # Store the joined formatted string as well
            CONFIG['agent_system_prompt_template'] = "\n".join(formatted_agent_list)
            logger.info(f"Formatted agent prompt template: {CONFIG['agent_system_prompt_template'][:100]}...")
        else:
            CONFIG['agent_system_prompt_template_list'] = ["You are a helpful assistant."]
            CONFIG['agent_system_prompt_template'] = "You are a helpful assistant." # Fallback
            logger.error("agent_prompt_template is not a list in config.json")

        # Ensure required keys are present
        required_keys = [
            'initial_message',
            'calendar_tool_description',
            'agent_system_prompt_template',
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

# Function to get config values
def get_config(key, default=None):
    return CONFIG.get(key, default) 