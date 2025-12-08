// Import the new AuthManager if available
let AuthManager;
try {
    const authModule = await import('./auth/manager.js');
    AuthManager = authModule.AuthManager;
} catch (e) {
    console.warn('AuthManager not found, falling back to legacy implementation');
}

// Simple PKCE helper for a pure client-side OIDC flow.
const OIDC_CODE_CHALLENGE_METHOD = "S256";
const STORAGE_KEY_VERIFIER = "pkce_code_verifier";

// Legacy provider configuration (kept for backward compatibility)
const PROVIDERS = {
    google: {
        authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
        scope: "openid email profile",
        basePath: "/auth/google",
        platforms: {
            web: {
                clientId: "YOUR_GOOGLE_WEB_CLIENT_ID",
                redirectPath: "/auth/google/callback",
            },
            ios: {
                clientId: "YOUR_GOOGLE_IOS_CLIENT_ID",
                redirectPath: "/auth/google/callback",
            },
            android: {
                clientId: "YOUR_GOOGLE_ANDROID_CLIENT_ID",
                redirectPath: "/auth/google/callback",
            },
        },
    },
    apple: {
        authorizationEndpoint: "https://appleid.apple.com/auth/authorize",
        scope: "openid email name",
        basePath: "/auth/apple",
        platforms: {
            web: {
                clientId: "YOUR_APPLE_WEB_CLIENT_ID",
                redirectPath: "/auth/apple/callback",
            },
            ios: {
                clientId: "YOUR_APPLE_IOS_CLIENT_ID",
                redirectPath: "/auth/apple/callback",
            },
            android: {
                clientId: "YOUR_APPLE_ANDROID_CLIENT_ID",
                redirectPath: "/auth/apple/callback",
            },
        },
    },
};

// Export the main authentication functions
export async function startLogin(provider, platform = 'web', state = '') {
    try {
        // Use the new AuthManager if available
        if (AuthManager) {
            await AuthManager.startLogin(provider, platform);
            return;
        }
        
        // Fallback to legacy implementation
        const verifier = await generateCodeVerifier();
        const challenge = await generateCodeChallenge(verifier);
        sessionStorage.setItem(STORAGE_KEY_VERIFIER, verifier);

        const config = getProviderConfig(provider, platform);
        const redirectUri = window.location.origin + config.redirectPath;
        
        const params = new URLSearchParams({
            client_id: config.clientId,
            redirect_uri: redirectUri,
            response_type: "code",
            scope: config.scope,
            state: state || '',
            code_challenge: challenge,
            code_challenge_method: OIDC_CODE_CHALLENGE_METHOD,
        });

        // Add provider-specific parameters
        if (provider === 'google') {
            params.append('access_type', 'offline');
            params.append('prompt', 'consent');
        } else if (provider === 'apple') {
            params.append('response_mode', 'form_post');
        }

        const authUrl = `${config.authorizationEndpoint}?${params.toString()}`;
        window.location.assign(authUrl);
    } catch (error) {
        console.error('Login failed:', error);
        throw error;
    }
}

export async function handleCallback() {
    try {
        // Use the new AuthManager if available
        if (AuthManager) {
            return await AuthManager.handleCallback();
        }
        
        // Fallback to legacy implementation
        const params = new URLSearchParams(window.location.search);
        const code = params.get('code');
        const state = params.get('state');
        const verifier = sessionStorage.getItem(STORAGE_KEY_VERIFIER);
        
        if (!code || !verifier) {
            throw new Error('Missing required parameters');
        }

        // Here you would typically exchange the code for tokens
        // This is a simplified example
        return { code, state };
    } catch (error) {
        console.error('Error handling callback:', error);
        throw error;
    } finally {
        sessionStorage.removeItem(STORAGE_KEY_VERIFIER);
    }
}

// Legacy functions (kept for backward compatibility)
export async function generateCodeVerifier() {
    const array = new Uint8Array(32);
    window.crypto.getRandomValues(array);
    return base64UrlEncode(array);
}

async function generateCodeChallenge(verifier) {
    const data = new TextEncoder().encode(verifier);
    const digest = await window.crypto.subtle.digest("SHA-256", data);
    return base64UrlEncode(new Uint8Array(digest));
}

function base64UrlEncode(buffer) {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary)
        .replace(/\+/g, '-')
        .replace(/\//g, '_')
        .replace(/=+$/, '');
}

export function getProviderConfig(provider, platform = 'web') {
    const providerCfg = PROVIDERS[provider];
    if (!providerCfg) {
        throw new Error(`Unknown provider: ${provider}`);
    }
    const platformCfg = providerCfg.platforms?.[platform];
    if (!platformCfg) {
        throw new Error(`Provider '${provider}' is not configured for platform '${platform}'`);
    }
    return {
        ...providerCfg,
        ...platformCfg,
        redirectPath: platformCfg.redirectPath || `/${provider}/callback`,
        clientId: platformCfg.clientId || providerCfg.clientId
    };
}

// Auto-handle the callback when the page loads
if (typeof window !== 'undefined' && window.location.search.includes('code=')) {
    handleCallback()
        .then(tokens => {
            // Store tokens and redirect
            localStorage.setItem('auth_tokens', JSON.stringify(tokens));
            const redirectUrl = new URLSearchParams(window.location.search).get('state') || '/';
            window.location.href = redirectUrl;
        })
        .catch(error => {
            console.error('Authentication failed:', error);
            window.location.href = `/login?error=${encodeURIComponent(error.message)}`;
        });
}

// Kept for backward compatibility
async function getConfig(provider, platform) {
    const basePath = `/auth/${provider}`;
    try {
        const response = await fetch(`${basePath}/config?platform=${platform}`);
        if (!response.ok) {
            throw new Error(`Failed to fetch ${provider} config: ${response.statusText}`);
        }
        const config = await response.json();
        return {
            authorizationEndpoint: config.authorization_endpoint,
            tokenEndpoint: config.token_endpoint,
            clientId: config.client_id,
            redirectUri: config.redirect_uri,
            scope: provider === config.scope,
            basePath: basePath,
            //redirectPath: `${basePath}/callback`
        };
    } catch (error) {
        console.error(`Error fetching ${provider} config:`, error);
        // Fallback to local config if server is not available
        const providerCfg = PROVIDERS[provider];
        if (!providerCfg) {
            throw new Error(`Unknown provider: ${provider}`);
        }
        const platformCfg = providerCfg.platforms?.[platform];
        if (!platformCfg) {
            throw new Error(`Provider '${provider}' is not configured for platform '${platform}'`);
        }
        throw new Error(`Error occured for provider '${provider}' and platform '${platform}'`);
    }
}

// Kept for backward compatibility
function getProviderConfig(provider, platform) {
    console.warn('getProviderConfig is deprecated. Use getConfig instead.');
    const providerCfg = PROVIDERS[provider];
    if (!providerCfg) {
        throw new Error(`Unknown provider: ${provider}`);
    }
    const platformCfg = providerCfg.platforms?.[platform];
    if (!platformCfg) {
        throw new Error(`Provider '${provider}' is not configured for platform '${platform}'`);
    }
    return {
        authorizationEndpoint: providerCfg.authorizationEndpoint,
        scope: providerCfg.scope,
        basePath: providerCfg.basePath,
        clientId: platformCfg.clientId,
        redirectPath: platformCfg.redirectPath,
    };
}

export async function startLogin(provider, platform, state) {
    const config = await getConfig(provider, platform);
    const verifier = await generateCodeVerifier();
    const challenge = await generateCodeChallenge(verifier);
    sessionStorage.setItem(STORAGE_KEY_VERIFIER, verifier);
    sessionStorage.setItem('oauth_config', JSON.stringify(config));

    const params = new URLSearchParams({
        client_id: config.clientId,
        redirect_uri: config.redirectUri || (window.location.origin + config.redirectPath),
        response_type: "code",
        scope,
        state,
        code_challenge: challenge,
        code_challenge_method: OIDC_CODE_CHALLENGE_METHOD,
    });

    const authUrl = `${authorizationEndpoint}?${params.toString()}`;
    console.log("Redirecting to OIDC auth endpoint", authUrl);
    window.location.assign(authUrl);
}
