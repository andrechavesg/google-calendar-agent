import * as fs from 'fs/promises';
import * as path from 'path';
import express from 'express';
import { OAuth2Client } from 'google-auth-library';
import { TokenManager } from './auth/tokenManager.js';
import open from 'open';
import { getKeysFilePath } from './auth/utils.js';

export class AuthServer {
  private server: express.Application | null = null;
  private httpServer: any = null;
  private tokenManager!: TokenManager;
  private port: number;
  private credentials: { client_id: string; client_secret: string } | null = null;
  private oauth2Client!: OAuth2Client;

  constructor() {
    this.port = 3000; // Start with default port
  }

  private async loadCredentials(): Promise<void> {
    const keysFilePath = getKeysFilePath();
    const content = await fs.readFile(keysFilePath, 'utf-8');
    const keys = JSON.parse(content);
    this.credentials = {
      client_id: keys.installed.client_id,
      client_secret: keys.installed.client_secret
    };
    console.log("OAuth credentials loaded successfully");
  }

  private createOAuthClient(port: number): OAuth2Client {
    if (!this.credentials) {
      console.error("Attempted to create OAuth client before loading credentials");
      throw new Error('Credentials not loaded');
    }
    return new OAuth2Client(
      this.credentials.client_id,
      this.credentials.client_secret,
      `http://localhost:${port}/oauth2callback`
    );
  }

  private async startServer(): Promise<boolean> {
    // Try ports 3000 and 3001
    const ports = [3000, 3001];
    
    for (const port of ports) {
      this.port = port;
      try {
        // 1. Recreate client for the current port
        this.oauth2Client = this.createOAuthClient(port);
        
        // 2. Recreate TokenManager with the *correct* client for this port attempt
        this.tokenManager = new TokenManager(this.oauth2Client); 
        
        this.server = express();
        
        // Handle OAuth callback
        this.server.get('/oauth2callback', async (req, res) => {
          try {
            const code = req.query.code as string;
            if (!code) {
              throw new Error('No code received');
            }

            // Use the correct TokenManager instance (implicitly `this.tokenManager`)
            const { tokens } = await this.oauth2Client.getToken(code);
            await this.tokenManager.saveTokens(tokens);
            
            console.log('Authentication successful. Tokens saved to disk'); 

            res.send('Authentication successful! You can close this window.');
            await this.stop();

          } catch (error: unknown) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
            console.error('Error in OAuth callback:', errorMessage);
            res.status(500).send('Authentication failed. Please try again.');
            await this.stop();
          }
        });

        // Try to start the server
        const serverStarted = await new Promise<boolean>((resolve) => {
          if (!this.server) {
            console.error('Server instance not created');
            resolve(false);
            return;
          }

          this.httpServer = this.server.listen(port, () => {
            console.log(`Auth server listening on port ${port}`);
            resolve(true);
          });

          this.httpServer.on('error', (error: any) => {
            if (error.code === 'EADDRINUSE') {
              console.log(`Port ${port} is in use, trying next port...`);
              resolve(false);
            } else {
              console.error(`Server error on port ${port}:`, error);
              resolve(false);
            }
          });
        });

        if (serverStarted) {
          console.log(`Auth server running successfully on port ${port}`);
          return true; // Successfully started on this port
        }
        // If not started, the loop continues to the next port
      } catch (error) {
        console.error(`Error initializing server on port ${port}:`, error);
      }
    }

    // If loop completes without starting
    console.error('Failed to start auth server on any available port (3000-3001)');
    return false;
  }

  public async start(): Promise<boolean> {
    console.log('Starting authentication process...');
    let areTokensValid = false;

    try {
        // 1. Load client ID/Secret first
        await this.loadCredentials();

        // 2. Configure the initial OAuth client
        this.oauth2Client = this.createOAuthClient(this.port); // Use default port initially

        // 3. Create TokenManager with the configured client
        this.tokenManager = new TokenManager(this.oauth2Client);

        // 4. Validate using the configured client and loaded tokens
        areTokensValid = await this.tokenManager.validateTokens();

        if (areTokensValid) {
            console.log('Existing tokens are valid. No need to start auth server');
            // Process should exit cleanly if tokens are valid
            process.exit(0);
        }
        // Only reach here if tokens are invalid/missing
        console.log('Authentication required. Starting auth flow...');
    } catch (error: unknown) {
        // Handle errors during credential loading or initial validation
        const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
        // Check if it's a file not found error for credentials
        const isCredentialsMissing = error instanceof Error && 'code' in error && error.code === 'ENOENT';
        console.log(`Initial validation failed (${isCredentialsMissing ? 'credentials file missing?' : 'validation error'}). Proceeding with authentication flow...`);
        // Allow falling through to start the full auth flow
    }

    // --- Authentication Flow --- 
    // Only reach here if tokens are invalid/missing or initial validation failed

    try {
        // Ensure credentials are loaded if the first block failed early
        if (!this.credentials) await this.loadCredentials();

        // Start the server, this might change this.oauth2Client and this.tokenManager
        const serverStarted = await this.startServer(); 
        if (!serverStarted) {
            console.error('Failed to start auth server after validation check');
            return false; // Explicitly return false if server fails to start
        }

        // --- Server is running, open browser --- 

        // Generate Auth URL with the *final* client instance (set by startServer)
        const authorizeUrl = this.oauth2Client.generateAuthUrl({
            access_type: 'offline',
            scope: ['https://www.googleapis.com/auth/calendar']
        });

        console.log(`Opening browser for authentication on port ${this.port}...`);
        await open(authorizeUrl);

        // Return true indicating the auth flow was successfully initiated
        // The process will wait for the callback or timeout in stop()
        return true; 

    } catch (error: unknown) {
        const errorMessage = error instanceof Error ? error.message : 'Unknown error occurred';
        console.error('Authentication initiation failed:', errorMessage);
        await this.stop(); // Attempt cleanup, which includes process.exit
        return false; // Return false on failure
    }
  }

  public async stop(): Promise<void> {
    if (this.httpServer) {
      return new Promise((resolve) => {
        // Add safety timeout to ensure process exits even if close callback doesn't fire
        const safetyTimeout = setTimeout(() => {
          console.log('Auth process completed, exiting...');
          process.exit(0);
        }, 1000); // Wait 1 second before forcing exit
        
        this.httpServer.close(() => {
          clearTimeout(safetyTimeout); // Clear the safety timeout if server closes properly
          this.server = null;
          this.httpServer = null;
          console.log('Auth process completed successfully');
          resolve();
          process.exit(0); // Exit successfully after stopping
        });
        
        this.httpServer.on('error', (error: any) => {
          clearTimeout(safetyTimeout); // Clear the safety timeout on error
          console.error('Error stopping auth server:', error);
          resolve();
          process.exit(1); // Exit with error if stopping fails
        });
      });
    } else {
      console.log('No server to stop');
      process.exit(0); // Exit successfully if no server was running
    }
  }
}

// For backwards compatibility with npm run auth
if (import.meta.url.endsWith('auth-server.js')) {
  const authServer = new AuthServer(); 
  authServer.start().catch(console.error);
}