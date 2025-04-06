# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Set the main application working directory
WORKDIR /usr/src/app

# --- Install Node.js ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl gnupg && \
    curl -fsSL https://deb.nodesource.com/setup_lts.x | bash - && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/*

# --- Install Python Dependencies (copy only requirements to leverage cache) ---
COPY requirements.txt /usr/src/app/requirements.txt
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# --- Build MCP Server inside Image (in a separate directory) ---
COPY ./mcp_server /usr/src/mcp_server
WORKDIR /usr/src/mcp_server
RUN npm install
RUN npm run build

# --- Copy Application Code ---
WORKDIR /usr/src/app
COPY ./app /usr/src/app
COPY ./config.json /usr/src/app/config.json

# --- Set Runtime Environment Variables ---
# Set the path for the MCP script *built inside the image* at its new location
ENV MCP_SERVER_SCRIPT_PATH=/usr/src/mcp_server/build/index.js

# Expose the port the app runs on
EXPOSE 3001

# Define the command to run the application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "3001"] 