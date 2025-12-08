import { GoogleOAuthProvider } from './providers/google.js';
import { AppleOAuthProvider } from './providers/apple.js';
import { MicrosoftOAuthProvider } from './providers/microsoft.js';

const PROVIDERS = {
  google: GoogleOAuthProvider,
  apple: AppleOAuthProvider,
  microsoft: MicrosoftOAuthProvider
};

export function getOAuthProvider(provider, config) {
  const ProviderClass = PROVIDERS[provider.toLowerCase()];
  if (!ProviderClass) {
    throw new Error(`Unsupported OAuth provider: ${provider}`);
  }
  return new ProviderClass(config);
}
