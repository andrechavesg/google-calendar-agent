import { OAuth2Client } from 'google-auth-library';
import * as fs from 'fs/promises';
import { getKeysFilePath } from './utils.js';

export async function initializeOAuth2Client(): Promise<OAuth2Client> {
  try {
    const keysContent = await fs.readFile(getKeysFilePath(), "utf-8");
    const keys = JSON.parse(keysContent);

    const { client_id, client_secret, redirect_uris } = keys.installed;

    return new OAuth2Client({
      clientId: client_id,
      clientSecret: client_secret,
      redirectUri: redirect_uris[0],
    });
  } catch (error) {
    console.error("Error loading OAuth keys:", error);
    throw error;
  }
} 