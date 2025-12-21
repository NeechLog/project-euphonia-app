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

      // Redirect to provider
      window.location.assign(url);
    } catch (error) {
      console.error('Login failed:', error);
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
