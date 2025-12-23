import { OAuthProvider } from './base.js';

export class MicrosoftOAuthProvider extends OAuthProvider {
  async startLogin(state, codeChallenge, codeChallengeMethod = 'S256') {
    const params = new URLSearchParams({
      client_id: this.config.client_id,
      response_type: 'code',
      redirect_uri: this.config.redirect_uri,
      scope: this.config.scope || 'openid profile email',
      state,
      code_challenge: codeChallenge,
      code_challenge_method: codeChallengeMethod,
      response_mode: 'query'
    });

    return {
      url: `${this.config.authorization_endpoint}?${params.toString()}`
    };
  }
}
