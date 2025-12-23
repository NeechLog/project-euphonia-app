import { OAuthProvider } from './base.js';

export class GoogleOAuthProvider extends OAuthProvider {
  async startLogin(state, codeChallenge, codeChallengeMethod = 'S256') {
    const params = new URLSearchParams({
      client_id: this.config.client_id,
      redirect_uri: this.config.redirect_uri,
      response_type: 'code',
      scope: this.config.scope || 'openid email profile',
      state,
      code_challenge: codeChallenge,
      code_challenge_method: codeChallengeMethod,
      access_type: 'offline',
      prompt: 'consent',
      include_granted_scopes: 'true'
    });

    return {
      url: `${this.config.authorization_endpoint}?${params.toString()}`
    };
  }
}
