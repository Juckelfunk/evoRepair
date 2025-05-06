import json
import os
import yaml
from pathlib import Path
import requests
from app import emitter, values
from dotenv import load_dotenv
from openai import OpenAI, OpenAIError
from google import genai
from google.api_core import exceptions as google_exceptions

def call_llm(prompt, llm_key=None):
    # Read config file
    # TODO: Ideally the LLM config integrity should be checked when the EvoRepair config is read
    config = read_config()
    if config is None:
        emitter.error("Failed to load LLM configuration.")
        return None

    # Determine which model to use via key
    if llm_key is None:
        llm_key = config.get("default")
    if not llm_key:
        emitter.error("No 'default' LLM specified in configuration and no llm_key provided.")
        return None
    emitter.information(f"LLM configuration: '{llm_key}'")

    # Get configuration for selected LLM
    llm_configs = config.get("llms", {})
    if llm_key not in llm_configs:
        emitter.error(f"LLM configuration key '{llm_key}' not found in config file.")
        return None
    selected_llm_config = llm_configs[llm_key]
    provider = selected_llm_config.get("provider")
    if not provider:
        emitter.error(f"Provider for LLM configuration '{llm_key}' not specified in configuration.")
        return None

    emitter.debug(f"Prompt:\n{prompt}")

    # Make API call
    if provider == "ollama":
        result = _call_ollama(prompt, selected_llm_config)
    elif provider == "gemini":
        result = _call_gemini(prompt, selected_llm_config)
    elif provider == "openai":
        result = _call_openai(prompt, selected_llm_config)
    else:
        emitter.error(f"Unsupported LLM provider: '{provider}' in configuration '{llm_key}'.")
        return None

    emitter.information(f"Input tokens: {result['input_tokens']} Output tokens: {result['output_tokens']}")
    emitter.debug(f"LLM response:\n{result['text']}")
    return result['text']

def read_config():
    if not Path(values.file_llm_config).is_file():
        emitter.error(f"LLM config file does not exist: {values.file_llm_config}")
        return None # TODO: Program should exit

    try:
        with open(values.file_llm_config, "r") as f:
            config = yaml.load(f, Loader=yaml.FullLoader)
        if not isinstance(config, dict):
            emitter.error(f"Invalid YAML format in {values.file_llm_config}. Root should be a dictionary.")
            return None
    except yaml.YAMLError as e:
        emitter.error(f"Error parsing YAML config file {values.file_llm_config}: {e}")
        return None
    except Exception as e:
        emitter.error(f"Failed to read config file {values.file_llm_config}: {e}")
        return None

    return config

def get_api_key(config):
    load_dotenv()  # Load .env file to include API keys in the environment.
    api_key_env = config.get("api_key_env")
    if not api_key_env:
        emitter.warning("API key environment variable not specified in configuration.")
        return None
    api_key = os.environ.get(api_key_env)
    if not api_key:
        emitter.warning(f"API key environment variable '{api_key_env}' not found.")
    return api_key

def _call_ollama(prompt, config):
    model_name = config.get("model")
    api_base = config.get("api_base") # Expecting http://host:port

    if not model_name:
         emitter.error("Ollama 'model' not specified in configuration.")
         return None
    if not api_base:
         emitter.error("Ollama 'api_base' (URL) not specified in configuration.")
         return None

    # Construct the full API endpoint URL
    api_base = api_base.rstrip('/')
    url = api_base + "/api/generate"

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False#,
        #"options": {"num_ctx": config.get("num_ctx", 4096)} # TODO: Should be in config, too
    }

    try:
        emitter.information(f"Calling Ollama model {model_name} at {url}")
        response = requests.post(url, data=json.dumps(payload))
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        response_data = response.json()

        response_text = ""
        input_tokens = 0
        output_tokens = 0

        if "response" in response_data:
             response_text = response_data["response"].strip()
             # Ollama provides token counts in the non-streaming response
             input_tokens = response_data.get("prompt_eval_count", 0)
             output_tokens = response_data.get("eval_count", 0)
        elif "error" in response_data:
             emitter.error(f"Ollama API returned an error: {response_data['error']}")
             return None
        else:
             emitter.warning("Unexpected response structure from Ollama.")
             response_text = str(response_data) # Return raw data as fallback

        return {
            "text": response_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    except requests.exceptions.ConnectionError:
        emitter.error(f"Connection Error: Could not connect to Ollama at {url}. Is the server running?")
        return None
    except requests.exceptions.RequestException as e:
        emitter.error(f"Request Error calling Ollama: {e}")
        return None
    except json.JSONDecodeError:
        emitter.error(f"JSON Decode Error: Invalid response from Ollama: {response.text}")
        return None
    except Exception as e:
        emitter.error(f"An unexpected error occurred calling Ollama: {e}")
        return None

def _call_gemini(prompt, config):
    api_key = get_api_key(config)
    if not api_key and config.get("api_key_env"):
         emitter.error(f"Gemini API key from env var '{config.get('api_key_env')}' is missing.")
         return None

    model_name = config.get("model")
    if not model_name:
         emitter.error("Gemini 'model' not specified in configuration.")
         return None

    try:
        client = genai.Client(api_key=api_key)
        emitter.information(f"Sending prompt to Google Gemini model: {model_name}")

        response = client.models.generate_content(model=model_name, contents=prompt)

        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata'):
             input_tokens = response.usage_metadata.prompt_token_count
             output_tokens = response.usage_metadata.candidates_token_count

        return {
            "text": response.text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens
        }

    except google_exceptions.PermissionDenied as e:
         emitter.error(f"Google API Permission Denied: Check API key and permissions. Details: {e}")
         return None
    except google_exceptions.ResourceExhausted as e:
        emitter.error(f"Google API Quota Exceeded. Details: {e}")
        return None
    except Exception as e:
        emitter.error(f"An unexpected error occurred calling Google Gemini: {e}")
        return None

def _call_openai(prompt, config):
    if not OpenAI:
        emitter.error("OpenAI library is not installed. Please install it: pip install openai")
        return None

    api_key = get_api_key(config)
    if not api_key and config.get("api_key_env"):
         emitter.warning(f"OpenAI API key from env var '{config.get('api_key_env')}' is missing.")

    model_name = config.get("model")
    if not model_name:
        emitter.error("OpenAI 'model' not specified in configuration.")
        return None

    try:
        client = OpenAI()
        emitter.information(f"Sending prompt to OpenAI model: {model_name}")

        response = client.responses.create(model=model_name, input=prompt)
        print(response)

        return {
            "text": response.output[0].content[0].text,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens
        }

    except OpenAIError as e:
        emitter.error(f"OpenAI API Error: {e}")
        return None
    except Exception as e:
        emitter.error(f"An unexpected error occurred calling OpenAI: {e}")
        return None
