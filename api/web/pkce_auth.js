// Simple PKCE helper for a pure client-side OIDC flow.
// Provider-specific configuration for Google and Apple.

const PROVIDERS = {
    google: {
        authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
        scope: "openid email profile",
        basePath: "/auth/google",
        platforms: {
            web: {
                clientId: "YOUR_GOOGLE_WEB_CLIENT_ID", // TODO: replace
                redirectPath: "/auth/google/callback",
            },
            ios: {
                clientId: "YOUR_GOOGLE_IOS_CLIENT_ID", // TODO: replace
                redirectPath: "/auth/google/callback",
            },
            android: {
                clientId: "YOUR_GOOGLE_ANDROID_CLIENT_ID", // TODO: replace
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
                clientId: "YOUR_APPLE_WEB_CLIENT_ID", // TODO: replace
                redirectPath: "/auth/apple/callback",
            },
            ios: {
                clientId: "YOUR_APPLE_IOS_CLIENT_ID", // TODO: replace
                redirectPath: "/auth/apple/callback",
            },
            android: {
                clientId: "YOUR_APPLE_ANDROID_CLIENT_ID", // TODO: replace
                redirectPath: "/auth/apple/callback",
            },
        },
    },
};
const OIDC_CODE_CHALLENGE_METHOD = "S256";

const STORAGE_KEY_VERIFIER = "pkce_code_verifier";

async function generateCodeVerifier() {
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
    let binary = "";
    buffer.forEach(b => binary += String.fromCharCode(b));
    return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

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
            redirectPath: `${basePath}/callback`
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
        return {
            authorizationEndpoint: providerCfg.authorizationEndpoint,
            tokenEndpoint: provider === 'google' 
                ? 'https://oauth2.googleapis.com/token' 
                : 'https://appleid.apple.com/auth/token',
            clientId: platformCfg.clientId,
            redirectUri: window.location.origin + platformCfg.redirectPath,
            scope: providerCfg.scope,
            basePath: providerCfg.basePath,
            redirectPath: platformCfg.redirectPath
        };
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
