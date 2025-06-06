import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  ListToolsRequestSchema,
  CallToolRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { OAuth2Client } from "google-auth-library";
import { fileURLToPath } from "url";

// Import modular components
import { initializeOAuth2Client } from './auth/client.js';
import { AuthServer } from './auth/server.js';
import { TokenManager } from './auth/tokenManager.js';
import { getToolDefinitions } from './handlers/listTools.js';
import { handleCallTool } from './handlers/callTool.js';

// --- Global Variables --- 
// Necessary because they are initialized in main and used in handlers/cleanup

// Create server instance (global for export)
const server = new Server(
  {
    name: "google-calendar",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

let oauth2Client: OAuth2Client;
let tokenManager: TokenManager;
let authServer: AuthServer;

// --- Main Application Logic --- 

console.error("MCP_SERVER_DEBUG: Script start...");

async function main() {
  console.error("MCP_SERVER_DEBUG: main() entered.");
  try {
    // 1. Initialize Authentication
    console.error("MCP_SERVER_DEBUG: Calling initializeOAuth2Client()...");
    oauth2Client = await initializeOAuth2Client();
    console.error("MCP_SERVER_DEBUG: initializeOAuth2Client() completed.");

    console.error("MCP_SERVER_DEBUG: Creating TokenManager...");
    tokenManager = new TokenManager(oauth2Client);
    console.error("MCP_SERVER_DEBUG: TokenManager created.");

    console.error("MCP_SERVER_DEBUG: Creating AuthServer...");
    authServer = new AuthServer(oauth2Client);
    console.error("MCP_SERVER_DEBUG: AuthServer created.");

    // 2. Ensure Authentication or Start Auth Server
    // validateTokens attempts to load/refresh first.
    // <<< TEST: Temporarily disable auth check to isolate stdio issues >>>
    if (!(await tokenManager.validateTokens())) { 
      console.error("Authentication required or token expired, starting auth server...");
      const success = await authServer.start(); // Tries ports 3000-3004
      if (!success) {
        console.error("Critical: Failed to start authentication server. Please check port availability (3000-3004) or existing auth issues.");
        // Exit because the server cannot function without potential auth
        process.exit(1);
      }
      // If the auth server starts, the user needs to interact with it.
      // The tool handler will reject calls until authentication is complete.
      console.error("Please authenticate via the browser link provided by the auth server.");
      // NOTE: In the subprocess setup, the auth server likely won't be accessible.
      // The user needs to ensure valid tokens exist in the mounted volume beforehand.
    }
    // <<< END TEST >>>

    // 3. Set up MCP Handlers
    
    console.error("MCP_SERVER_DEBUG: Setting up MCP handlers...");
    
    // List Tools Handler
    server.setRequestHandler(ListToolsRequestSchema, async () => {
      // Directly return the definitions from the handler module
      return getToolDefinitions();
    });

    // Call Tool Handler
    server.setRequestHandler(CallToolRequestSchema, async (request) => {
      // Delegate the actual tool execution to the specialized handler
      return handleCallTool(request, oauth2Client);
    });

    console.error("MCP_SERVER_DEBUG: MCP handlers set up.");

    // 4. Connect Server Transport
    console.error("MCP_SERVER_DEBUG: Creating StdioServerTransport...");
    const transport = new StdioServerTransport();
    console.error("MCP_SERVER_DEBUG: StdioServerTransport created.");

    console.error("MCP_SERVER_DEBUG: Attempting server.connect(transport)...");
    await server.connect(transport);
    console.error("MCP_SERVER_DEBUG: server.connect(transport) completed."); // <<< Will likely not be reached if it hangs

    // 5. Set up Graceful Shutdown
    process.on("SIGINT", cleanup);
    process.on("SIGTERM", cleanup);

  } catch (error: unknown) {
    console.error("Server startup failed:", error instanceof Error ? error.message : error);
    process.exit(1);
  }
}

// --- Cleanup Logic --- 

async function cleanup() {
  console.error("\nShutting down gracefully...");
  try {
  if (authServer) {
        // Attempt to stop the auth server if it exists and might be running
    await authServer.stop();
  }
    // No need to clear tokens; let them persist for the next run.
    console.error("Cleanup complete.");
    process.exit(0);
  } catch (error: unknown) {
    console.error("Error during cleanup:", error instanceof Error ? error.message : error);
    process.exit(1); // Exit with error on cleanup failure
  }
}

// --- Exports & Execution Guard --- 

// Export server and main for testing or potential programmatic use
export { main, server };

// Run main() only when this script is executed directly
const isDirectRun = import.meta.url.startsWith('file://') && process.argv[1] === fileURLToPath(import.meta.url);
if (isDirectRun) {
  main().catch((error: unknown) => {
    // Catch unhandled errors from main's async execution
    console.error("Fatal error during main execution:", error instanceof Error ? error.message : error);
  process.exit(1);
});
}
