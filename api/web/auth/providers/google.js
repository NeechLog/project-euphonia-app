import { OAuthProvider } from './base.js';

export class GoogleOAuthProvider extends OAuthProvider {
  async startLogin(state) {
    //const verifier = await this.generateCodeVerifier();
    //const challenge = await this.generateCodeChallenge(verifier);
    
    const params = new URLSearchParams({
      client_id: this.config.client_id,
      redirect_uri: this.config.redirect_uri,
      response_type: 'code',
      scope: this.config.scope || 'openid email profile',
      state,
      code_challenge: challenge,
      code_challenge_method: 'S256',
      access_type: 'offline',
      prompt: 'consent',
      include_granted_scopes: 'true'
    });

    return {
      url: `${this.config.authorization_endpoint}?${params.toString()}`,
      verifier
    };
  }

  async exchangeCode(code, verifier) {
    const response = await fetch(this.config.token_endpoint, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: this.config.client_id,
        client_secret: this.config.client_secret,
        code,
        grant_type: 'authorization_code',
        redirect_uri: this.config.redirect_uri,
        code_verifier: verifier
      })
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error_description || 'Failed to exchange code for token');
    }

    return response.json();
  }
}
