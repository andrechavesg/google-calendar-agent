# Calendar Agent

A conversational AI agent built with LangChain, FastAPI, and OpenAI, designed to interact with Google Calendar for scheduling consultations and managing events via a web interface. It uses a separate Node.js Microservice Proxy (MCP) server to handle Google Calendar API interactions securely.

## Prerequisites

*   **Docker:** [Install Docker](https://docs.docker.com/get-docker/)
*   **Docker Compose:** Usually included with Docker Desktop. [Install Docker Compose](https://docs.docker.com/compose/install/) if needed.
*   **Git:** To clone the repository.
*   **Google Cloud Credentials:** You need API credentials to allow the MCP server to access Google Calendar.
    *   Follow the Google Cloud guide to [create credentials for a service account](https://cloud.google.com/iam/docs/creating-managing-service-account-keys) or [OAuth 2.0 Client ID](https://developers.google.com/workspace/guides/create-credentials#oauth-client-id) suitable for your authentication method within the MCP server.
    *   Download the credential JSON file.

## Setup

1.  **Clone the repository:**
    ```bash
    git clone <repository_url>
    cd calendar-agent
    ```

2.  **Place Google Credentials:**
    *   Rename your downloaded Google Cloud credential JSON file to `google_credentials.json`.
    *   Place this file inside the `.credentials/` directory:
        ```
        mv /path/to/your/downloaded_credentials.json ./.credentials/google_credentials.json
        ```
    *   *Note: The `.credentials/` directory is included in `.gitignore` to prevent accidentally committing sensitive keys.*

3.  **Configure Environment Variables:**
    *   Create a `.env` file in the project root (`calendar-agent/`).
    *   Add the following variables, replacing the placeholder values:
        ```dotenv
        # .env
        OPENAI_API_KEY=your_openai_api_key_here
        # This tells the Google libraries inside the container where to find the credentials
        GOOGLE_APPLICATION_CREDENTIALS=/usr/src/app/.credentials/google_credentials.json
        # Add any other environment variables required by MCP server if applicable
        ```
    *   Replace `your_openai_api_key_here` with your actual OpenAI API key.

## Configuration (`config.json`)

Adjust the agent's behavior and UI elements by modifying `calendar-agent/config.json`. Key options include:

*   `display_timezone_short`, `display_timezone_long`, `display_timezone_utc`, `internal_timezone_id`: Timezone settings for display and internal calculations.
*   `consultation_duration_minutes`: Default duration for scheduled consultations.
*   `chat_title`: Title displayed in the web UI header.
*   `input_placeholder`: Placeholder text in the chat input field.
*   `default_calendar_id`: The Google Calendar ID used by default for checking availability and scheduling (e.g., `your_email@example.com`).
*   `default_event_title`: Default title for newly created consultation events.
*   `initial_message`: The first message the bot sends in the chat.
*   `agent_prompt_template`: The main instruction set defining the agent's behavior, workflow, and language. Placeholders like `{consultation_duration_minutes}`, `{default_calendar_id}`, etc., defined elsewhere in the config will be automatically substituted here.

## Running the Application (Docker Compose)

Docker Compose handles building the `mcp-server` Node.js service and the `calendar-agent` Python service, along with managing dependencies and networking.

**Option 1: Standard Run (Production-like)**

This command builds the images if they don't exist and starts both services in the background.

```bash
docker compose up --build -d
```

**Option 2: Development with Hot Reloading (Python App)**

For development, you often want the Python FastAPI application (`calendar-agent` service) to automatically restart when you make code changes in the `app/` directory. To enable this:

1.  **Modify `docker-compose.yml`:**
    *   Add a `command` directive to the `calendar-agent` service to override the default `Dockerfile` `CMD` and run `uvicorn` with the `--reload` flag.

    ```yaml
    # docker-compose.yml
    services:
      mcp-server:
        # ... (mcp-server configuration remains the same) ...
        build: ./mcp_server
        # ...

      calendar-agent:
        build:
          context: .
          dockerfile: Dockerfile
        ports:
          - "3001:3001"
        env_file:
          - .env
        volumes:
          - ./app:/usr/src/app  # Mount app directory for code changes
          - ./.credentials:/usr/src/app/.credentials:ro # Mount credentials read-only
        depends_on:
          - mcp-server
        # Add this command for hot reloading:
        command: ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001", "--reload"]

    ```

2.  **Run Docker Compose:**
    ```bash
    docker compose up --build
    ```
    *   Run this *without* the `-d` flag initially to see the logs and confirm `uvicorn` starts with the reload notice.
    *   Now, any changes saved to files within the `calendar-agent/app/` directory on your host machine will trigger an automatic restart of the `calendar-agent` service inside the container.

*   *Note:* Hot reloading only applies to the Python code in `app/`. Changes to `config.json`, `.env`, `requirements.txt`, `Dockerfile`, `docker-compose.yml`, or the `mcp_server` code will still require a manual rebuild and restart (`docker compose down && docker compose up --build`).

## Accessing the Chat Interface

Once the services are running, access the web UI in your browser:

[http://localhost:3001](http://localhost:3001)

## Stopping the Application

To stop the running services:

```bash
docker compose down
```

To stop and remove the volumes (clearing chat history if stored in a volume, though currently it seems in-memory):

```bash
docker compose down -v
``` 