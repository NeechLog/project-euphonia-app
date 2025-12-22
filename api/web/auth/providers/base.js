export class OAuthProvider {
  constructor(config) {
    this.config = config;
  }

  async startLogin() {
    throw new Error('Not implemented');
  }

  async exchangeCode() {
    throw new Error('Not implemented');
  }
}
