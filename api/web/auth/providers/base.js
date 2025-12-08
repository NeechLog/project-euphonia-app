export class OAuthProvider {
  constructor(config) {
    this.config = config;
  }

  async generateCodeVerifier() {
    const array = new Uint8Array(32);
    window.crypto.getRandomValues(array);
    return this.base64UrlEncode(array);
  }

  async generateCodeChallenge(verifier) {
    const data = new TextEncoder().encode(verifier);
    const digest = await window.crypto.subtle.digest('SHA-256', data);
    return this.base64UrlEncode(new Uint8Array(digest));
  }

  base64UrlEncode(buffer) {
    let binary = '';
    buffer.forEach(b => binary += String.fromCharCode(b));
    return btoa(binary)
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
  }

  async startLogin() {
    throw new Error('Not implemented');
  }

  async exchangeCode() {
    throw new Error('Not implemented');
  }
}
