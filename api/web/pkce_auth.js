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

function getProviderConfig(provider, platform) {
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
    const { authorizationEndpoint, clientId, scope, redirectPath } = getProviderConfig(provider, platform);
    const redirectUri = window.location.origin + redirectPath;
    const verifier = await generateCodeVerifier();
    const challenge = await generateCodeChallenge(verifier);
    sessionStorage.setItem(STORAGE_KEY_VERIFIER, verifier);

    const params = new URLSearchParams({
        client_id: clientId,
        redirect_uri: redirectUri,
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
