// Simple PKCE helper for a pure client-side OIDC flow.
// Provider-specific configuration for Google and Apple.

const PROVIDERS = {
    google: {
        authorizationEndpoint: "https://accounts.google.com/o/oauth2/v2/auth",
        clientId: "YOUR_GOOGLE_CLIENT_ID", // TODO: replace
        scope: "openid email profile",
        basePath: "/auth/google",
    },
    apple: {
        authorizationEndpoint: "https://appleid.apple.com/auth/authorize",
        clientId: "YOUR_APPLE_CLIENT_ID", // TODO: replace
        scope: "openid email name",
        basePath: "/auth/apple",
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

function getProviderConfig(provider) {
    const cfg = PROVIDERS[provider];
    if (!cfg) {
        throw new Error(`Unknown provider: ${provider}`);
    }
    return cfg;
}

export async function startLogin(provider, state, redirectUri) {
    const { authorizationEndpoint, clientId, scope } = getProviderConfig(provider);
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
