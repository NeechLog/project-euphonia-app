import { OAuthProvider } from './base.js';

export class AppleOAuthProvider extends OAuthProvider {
  async startLogin(state, codeChallenge, codeChallengeMethod = 'S256') {
    const params = new URLSearchParams({
      client_id: this.config.client_id,
      redirect_uri: this.config.redirect_uri,
      response_type: 'code',
      scope: this.config.scope || 'name email',
      state,
      code_challenge: codeChallenge,
      code_challenge_method: codeChallengeMethod,
      response_mode: 'form_post'
    });

    return {
      url: `${this.config.authorization_endpoint}?${params.toString()}`
    };
  }
}
