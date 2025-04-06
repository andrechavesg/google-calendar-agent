import express from 'express';
import { OAuth2Client } from 'google-auth-library';
import { TokenManager } from './tokenManager.js';
import http from 'http';
import url from 'url';

export class AuthServer {
  private oauth2Client: OAuth2Client;
  private app: express.Express;
  private server: http.Server | null = null;
  private tokenManager: TokenManager;

  constructor(oauth2Client: OAuth2Client) {
    this.oauth2Client = oauth2Client;
    this.tokenManager = new TokenManager(oauth2Client);
    this.app = express();
    this.setupRoutes();
  }

  private setupRoutes(): void {
    this.app.get('/', (req, res) => {
      const scopes = ['https://www.googleapis.com/auth/calendar'];
      const authUrl = this.oauth2Client.generateAuthUrl({
        access_type: 'offline',
        scope: scopes,
        prompt: 'consent' // Force consent screen for refresh token
      });
      res.send(`<h1>Google Calendar Authentication</h1><a href="${authUrl}">Authenticate with Google</a>`);
    });

    this.app.get('/oauth2callback', async (req, res) => {
      const code = req.query.code as string;
      if (!code) {
        res.status(400).send('Authorization code missing');
        return;
      }
      try {
        const { tokens } = await this.oauth2Client.getToken(code);
        await this.tokenManager.saveTokens(tokens);
        res.send('Authentication successful! You can close this window.');
        // Optionally stop the server after successful auth
        // this.stop(); 
      } catch (error: unknown) {
        console.error('Error retrieving access token', error);
        res.status(500).send('Authentication failed');
      }
    });
  }

  async start(startPort = 3000, endPort = 3004): Promise<boolean> {
    for (let port = startPort; port <= endPort; port++) {
        try {
            await new Promise<void>((resolve, reject) => {
                this.server = this.app.listen(port, () => {
                    console.error(`Auth server listening on http://localhost:${port}`);
                    resolve();
                });
                this.server.on('error', (err: NodeJS.ErrnoException) => {
                    if (err.code === 'EADDRINUSE') {
                        console.error(`Port ${port} already in use, trying next...`);
                        this.server?.close();
                        reject(err);
                    } else {
                        console.error('Auth server error:', err);
                        reject(err);
                    }
                });
            });
            return true;
        } catch (error: unknown) {
            if (!(error instanceof Error && 'code' in error && error.code === 'EADDRINUSE')) {
                return false;
            }
        }
    }
    console.error(`Failed to start auth server on ports ${startPort}-${endPort}.`);
    return false;
  }

  public getRunningPort(): number | null {
    if (this.server) {
        const address = this.server.address();
        if (typeof address === 'object' && address !== null) {
            return address.port;
        }
    }
    return null;
  }

  async stop(): Promise<void> {
    return new Promise((resolve, reject) => {
      if (this.server) {
        this.server.close((err) => {
          if (err) {
            console.error("Error stopping auth server:", err);
            reject(err);
          } else {
            console.error("Auth server stopped.");
            this.server = null;
            resolve();
          }
        });
      } else {
        resolve();
      }
    });
  }
} 