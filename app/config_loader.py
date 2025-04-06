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

        # Format qualification agent prompt template safely
        if isinstance(raw_config.get('qualification_agent_prompt_template'), list):
            qual_template_list = raw_config['qualification_agent_prompt_template']
            formatted_qual_list = [
                safe_formatter.format(line, **raw_config) for line in qual_template_list
            ]
            CONFIG['qualification_agent_system_prompt_template_list'] = formatted_qual_list
            CONFIG['qualification_agent_system_prompt_template'] = "\n".join(formatted_qual_list)
            logger.info(f"Formatted qualification agent prompt template: {CONFIG['qualification_agent_system_prompt_template'][:100]}...")
        else:
            CONFIG['qualification_agent_system_prompt_template_list'] = ["Error loading qualification prompt."]
            CONFIG['qualification_agent_system_prompt_template'] = "Error loading qualification prompt."
            logger.error("qualification_agent_prompt_template is not a list or not found in config.json")

        # Format scheduling agent prompt template safely (renamed from agent_prompt_template)
        if isinstance(raw_config.get('scheduling_agent_prompt_template'), list):
            sched_template_list = raw_config['scheduling_agent_prompt_template']
            # Format each line using safe_formatter and the entire raw_config
            formatted_sched_list = [
                safe_formatter.format(line, **raw_config) for line in sched_template_list
            ]
            # Store the list of formatted strings
            CONFIG['scheduling_agent_system_prompt_template_list'] = formatted_sched_list
            # Store the joined formatted string as well
            CONFIG['scheduling_agent_system_prompt_template'] = "\n".join(formatted_sched_list)
            logger.info(f"Formatted scheduling agent prompt template: {CONFIG['scheduling_agent_system_prompt_template'][:100]}...")
        else:
            # Use a sensible default if the scheduling template is missing
            default_scheduling_prompt = "You are a helpful assistant designed to schedule meetings."
            CONFIG['scheduling_agent_system_prompt_template_list'] = [default_scheduling_prompt]
            CONFIG['scheduling_agent_system_prompt_template'] = default_scheduling_prompt # Fallback
            logger.error("scheduling_agent_prompt_template is not a list or not found in config.json")

        # Ensure required keys are present (adjust required keys)
        required_keys = [
            'initial_message',
            'calendar_tool_description',
            'qualification_agent_system_prompt_template',
            'scheduling_agent_system_prompt_template',
            'qualification_api_url',
            'not_qualified_message',
            'not_qualified_pdf_url',
            'max_calendar_result_length',
            'vector_store_tool_description',
            'vector_store_data_url'
        ]
        for key in required_keys:
             if key not in CONFIG:
                  logger.error(f"Missing required key '{key}' in loaded config.")
                  # Handle missing essential config appropriately
                  if key == 'qualification_agent_system_prompt_template': CONFIG[key] = "Error loading qualification prompt."
                  if key == 'scheduling_agent_system_prompt_template': CONFIG[key] = "You are a helpful assistant designed to schedule meetings."
                  if key == 'calendar_tool_description': CONFIG[key] = "Calendar tool."
                  # Add handling for other new required keys if necessary
                  if key == 'vector_store_tool_description': CONFIG[key] = "Vector store tool description missing."
                  if key == 'vector_store_data_url': CONFIG[key] = ""

        logger.info("Configuration loaded successfully.")

    except FileNotFoundError:
        logger.error(f"Configuration file not found at {config_path}")
        CONFIG = {
            'agent_system_prompt_template': "You are a helpful assistant.",
            'qualification_agent_system_prompt_template': "Error loading qualification prompt.",
            'scheduling_agent_system_prompt_template': "You are a helpful assistant designed to schedule meetings.",
            'calendar_tool_description': "Calendar tool.",
            'initial_message': "Error loading config.",
            'qualification_api_url': '',
            'not_qualified_message': 'Could not qualify.',
            'not_qualified_pdf_url': '',
            'vector_store_tool_description': 'Vector store tool description missing.',
            'vector_store_data_url': ''
        }
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {config_path}")
        CONFIG = {
            'agent_system_prompt_template': "You are a helpful assistant.",
            'qualification_agent_system_prompt_template': "Error loading qualification prompt.",
            'scheduling_agent_system_prompt_template': "You are a helpful assistant designed to schedule meetings.",
            'calendar_tool_description': "Calendar tool.",
            'initial_message': "Error loading config.",
            'qualification_api_url': '',
            'not_qualified_message': 'Could not qualify.',
            'not_qualified_pdf_url': '',
            'vector_store_tool_description': 'Vector store tool description missing.',
            'vector_store_data_url': ''
        }
    except Exception as e:
        logger.exception(f"An unexpected error occurred loading configuration: {e}")
        CONFIG = {
            'agent_system_prompt_template': "You are a helpful assistant.",
            'qualification_agent_system_prompt_template': "Error loading qualification prompt.",
            'scheduling_agent_system_prompt_template': "You are a helpful assistant designed to schedule meetings.",
            'calendar_tool_description': "Calendar tool.",
            'initial_message': "Error loading config.",
            'qualification_api_url': '',
            'not_qualified_message': 'Could not qualify.',
            'not_qualified_pdf_url': '',
            'vector_store_tool_description': 'Vector store tool description missing.',
            'vector_store_data_url': ''
        }

# Load config when module is imported
load_config()

# Function to get config values
def get_config(key, default=None):
    return CONFIG.get(key, default) 