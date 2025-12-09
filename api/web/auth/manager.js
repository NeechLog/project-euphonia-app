import { getOAuthProvider } from './index.js';

const STORAGE_KEYS = {
  VERIFIER: 'pkce_verifier',
  CONFIG: 'oauth_config',
  STATE: 'oauth_state'
};

export class AuthManager {
  static async startLogin(provider, platform) {
    try {
      // Get configuration from server
      const config = await this.getConfig(provider, platform);
      const oauthProvider = getOAuthProvider(provider, config);
      
      // Generate state and get auth URL
      const state = await this.generateState(provider, platform);
      const { url, verifier } = await oauthProvider.startLogin(state);
      console.log("URL is " + url + "and why do we need this verifier" + verifier);
      // Store verifier and config securely
      sessionStorage.setItem(STORAGE_KEYS.VERIFIER, verifier);
      sessionStorage.setItem(STORAGE_KEYS.CONFIG, JSON.stringify(config));
      sessionStorage.setItem(STORAGE_KEYS.STATE, state);

      // Redirect to provider
      window.location.assign(url);
    } catch (error) {
      console.error('Login failed:', error);
      throw error;
    }
  }

  static async handleCallback() {
    try {
      const params = new URLSearchParams(window.location.search);
      const code = params.get('code');
      const state = params.get('state');
      
      // Verify state matches
      const savedState = sessionStorage.getItem(STORAGE_KEYS.STATE);
      if (state !== savedState) {
        throw new Error('Invalid state parameter');
      }

      // Get stored verifier and config
      const verifier = sessionStorage.getItem(STORAGE_KEYS.VERIFIER);
      const config = JSON.parse(sessionStorage.getItem(STORAGE_KEYS.CONFIG));
      
      if (!verifier || !config) {
        throw new Error('No active OAuth session found');
      }

      // Exchange code for tokens
      const oauthProvider = getOAuthProvider(config.provider, config);
      const tokens = await oauthProvider.exchangeCode(code, verifier);

      // Clean up
      this.clearSession();

      return tokens;
    } catch (error) {
      console.error('Error handling OAuth callback:', error);
      this.clearSession();
      throw error;
    }
  }

  static clearSession() {
    sessionStorage.removeItem(STORAGE_KEYS.VERIFIER);
    sessionStorage.removeItem(STORAGE_KEYS.CONFIG);
    sessionStorage.removeItem(STORAGE_KEYS.STATE);
  }

  static async generateState(provider, platform) {
    try {
      const response = await fetch(`/auth/${provider}/state?platform=${platform}`);
      if (!response.ok) {
        throw new Error('Failed to generate state');
      }
      const data = await response.json();
      return data.state;
    } catch (error) {
      console.error('Error fetching state from server, falling back to client-side generation:', error);
      // Fallback to client-side generation if server request fails
      return Math.random().toString(36).substring(2, 15) + 
             Math.random().toString(36).substring(2, 15);
    }
  }

  static async getConfig(provider, platform) {
    const response = await fetch(`/auth/${provider}/config?platform=${platform}`);
    if (!response.ok) {
      throw new Error('Failed to fetch OAuth configuration');
    }
    const config = await response.json();
    return {
      ...config,
      provider: provider.toLowerCase()
    };
  }
}
