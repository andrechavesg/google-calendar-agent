import * as path from 'path';
// No longer need fileURLToPath as we use a fixed path
// import { fileURLToPath } from 'url';

// Define the base path for credentials within the container/runtime environment
// Allow overriding via environment variable for local auth script execution
const DEFAULT_CREDENTIALS_DIR = '/usr/src/app/.credentials';
const CREDENTIALS_DIR = process.env.MCP_CREDENTIALS_DIR || DEFAULT_CREDENTIALS_DIR;

// Remove getProjectRoot as it's unreliable across environments
// function getProjectRoot() {
//   const __dirname = path.dirname(fileURLToPath(import.meta.url));
//   const projectRoot = path.join(__dirname, "..");
//   return path.resolve(projectRoot);
// }

// Returns the absolute path for the saved token file.
export function getSecureTokenPath(): string {
  // const projectRoot = getProjectRoot();
  // const tokenPath = path.join(projectRoot, ".gcp-saved-tokens.json");
  const tokenPath = path.join(CREDENTIALS_DIR, '.gcp-saved-tokens.json');
  console.error(`DEBUG: Using token path: ${tokenPath}`); // Add debug log
  return tokenPath;
}

// Returns the absolute path for the GCP OAuth keys file.
export function getKeysFilePath(): string {
  // const projectRoot = getProjectRoot();
  // const keysPath = path.join(projectRoot, "gcp-oauth.keys.json");
  const keysPath = path.join(CREDENTIALS_DIR, 'gcp-oauth.keys.json');
  console.error(`DEBUG: Using keys path: ${keysPath}`); // Add debug log
  return keysPath;
} 