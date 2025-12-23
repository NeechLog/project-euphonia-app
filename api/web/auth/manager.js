import { getOAuthProvider } from './index.js';

const STORAGE_KEYS = {
  VERIFIER: 'pkce_verifier',
  CONFIG: 'oauth_config',
  STATE: 'oauth_state'
};

export class AuthManager {
  static base64UrlEncode(buffer) {
    let binary = '';
    buffer.forEach(b => binary += String.fromCharCode(b));
    return btoa(binary)
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
  }

  static async generateCodeVerifier() {
    const array = new Uint8Array(32);
    window.crypto.getRandomValues(array);
    return this.base64UrlEncode(array);
  }

  static async generateCodeChallenge(verifier) {
    const data = new TextEncoder().encode(verifier);
    const digest = await window.crypto.subtle.digest('SHA-256', data);
    return this.base64UrlEncode(new Uint8Array(digest));
  }

  static async startLogin(provider, platform) {
    try {
      // Get configuration from server
      const config = await this.getConfig(provider, platform);
      const oauthProvider = getOAuthProvider(provider, config);
      
      // Generate state and get auth URL
      const codeVerifier = await this.generateCodeVerifier();
      const codeChallenge = await this.generateCodeChallenge(codeVerifier);
      const state = await this.generateState(provider, platform, codeVerifier);
      const { url } = await oauthProvider.startLogin(state, codeChallenge, 'S256');

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

  static async generateState(provider, platform, codeVerifier) {
    try {
      const response = await fetch(`/auth/${provider}/state`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          platform,
          code_verifier: codeVerifier,
        })
      });
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
