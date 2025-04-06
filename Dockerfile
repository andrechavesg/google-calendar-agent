# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /usr/src/app

# --- Install Node.js ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# --- Install Python Dependencies ---
COPY requirements.txt /usr/src/app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# --- Build MCP Server inside Image ---
COPY ./mcp_server /usr/src/app/mcp_server
WORKDIR /usr/src/app/mcp_server
RUN npm install
RUN npm run build
# Return to main workdir
WORKDIR /usr/src/app

# --- Copy Application Code ---
COPY ./app /usr/src/app/app
COPY ./calendar_tool_description.txt /usr/src/app/calendar_tool_description.txt
COPY ./agent_prompt.txt /usr/src/app/agent_prompt.txt

# --- Set Runtime Environment Variables ---
# Set the path for the MCP script *built inside the image*
ENV MCP_SERVER_SCRIPT_PATH=/usr/src/app/mcp_server/build/index.js

# Expose the port the app runs on
EXPOSE 3001

# Define the command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3001"] 