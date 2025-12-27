// Login/Authentication JavaScript
// Check login state on page load
document.addEventListener('DOMContentLoaded', function() {
    checkLoginState();
});

// Function to check current login state
async function checkLoginState() {
    try {
        const response = await fetch('/user/current');
        const data = await response.json();
        
        if (data.loggedIn && data.user) {
            showLoggedInState(data.user);
        } else {
            showLoggedOutState();
        }
    } catch (error) {
        console.error('Error checking login state:', error);
        showLoggedOutState();
    }
}

// Function to show logged in state
function showLoggedInState(user) {
    const authContainer = document.getElementById('authContainer');
    authContainer.innerHTML = `
        <div class="user-info">
            <span>Hello <strong>${user.Name || 'User'}</strong></span>
            <button class="login-btn logout-btn" onclick="handleLogout()">Logout</button>
        </div>
    `;
    hideLoginPopup();
}

// Function to show logged out state
function showLoggedOutState() {
    const authContainer = document.getElementById('authContainer');
    authContainer.innerHTML = `
        <button class="login-btn" onclick="toggleLoginPopup()">Login</button>
    `;
}

// Function to dynamically load scripts from HTML
async function loadScriptsFromHTML(htmlContent, container) {
    // Create a temporary DOM element to parse the HTML
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = htmlContent;
    
    // Find all script tags
    const scripts = tempDiv.querySelectorAll('script');
    
    // Load each script
    for (const script of scripts) {
        try {
            if (script.src) {
                // External script
                if (!loadedScripts.has(script.src)) {
                    await loadExternalScript(script.src, script.type);
                    loadedScripts.add(script.src);
                } else {
                    console.log(`Script already loaded, skipping: ${script.src}`);
                }
            } else if (script.textContent) {
                // Inline script - generate unique ID based on content
                const scriptId = 'inline_' + btoa(script.textContent.substring(0, 100)).replace(/[^a-zA-Z0-9]/g, '');
                if (!loadedScripts.has(scriptId)) {
                    if (script.type === 'module') {
                        // For module scripts, we need to create a blob URL
                        const blob = new Blob([script.textContent], { type: 'application/javascript' });
                        const moduleUrl = URL.createObjectURL(blob);
                        await loadExternalScript(moduleUrl, 'module');
                        URL.revokeObjectURL(moduleUrl);
                    } else {
                        // Regular inline script
                        const newScript = document.createElement('script');
                        newScript.textContent = script.textContent;
                        if (script.type) newScript.type = script.type;
                        container.appendChild(newScript);
                    }
                    loadedScripts.add(scriptId);
                } else {
                    console.log(`Inline script already loaded, skipping: ${scriptId}`);
                }
            }
        } catch (error) {
            console.error('Error loading script:', error);
        }
    }
}

// Function to load external script
function loadExternalScript(src, type = null) {
    return new Promise((resolve, reject) => {
        console.log(`Loading script: ${src} (type: ${type || 'default'})`);
        
        // For ES modules, try dynamic import first
        if (type === 'module' && src.startsWith('/')) {
            try {
                console.log(`Attempting dynamic import for module: ${src}`);
                // Convert relative path to absolute URL for dynamic import
                const absoluteUrl = window.location.origin + src;
                import(absoluteUrl).then(resolve).catch(reject);
                return;
            } catch (e) {
                console.warn(`Dynamic import failed for ${src}, falling back to script tag:`, e);
                // Fallback to script tag if import fails
            }
        }
        
        const script = document.createElement('script');
        script.src = src;
        if (type) script.type = type;
        
        script.onload = () => {
            console.log(`Successfully loaded script: ${src}`);
            resolve();
        };
        script.onerror = (error) => {
            console.error(`Failed to load script: ${src}`, error);
            reject(error);
        };
        
        document.head.appendChild(script);
    });
}

// Track loaded scripts to avoid duplicates
const loadedScripts = new Set();

// Function to toggle login popup
async function toggleLoginPopup() {
    const popup = document.getElementById('loginPopup');
    
    if (popup.classList.contains('show')) {
        popup.classList.remove('show');
    } else {
        try {
            // Check if login content is already loaded
            if (popup.innerHTML.trim() === '' || !popup.querySelector('button[id^="login"]')) {
                const response = await fetch('/login');
                const html = await response.text();
                
                // Set the HTML content
                popup.innerHTML = html;
                
                // Load and execute scripts from the HTML
                await loadScriptsFromHTML(html, popup);
            }
            
            popup.classList.add('show');
        } catch (error) {
            console.error('Error loading login form:', error);
            popup.innerHTML = '<div class="login-form"><h3 class="text-lg font-semibold mb-3">Login</h3><p>Error loading login form. Please try again later.</p></div>';
            popup.classList.add('show');
        }
    }
}

// Function to handle logout
async function handleLogout() {
    try {
        // Call logout endpoint
        const response = await fetch('/logout', {
            method: 'POST',
            credentials: 'include',
            headers: {
                'Content-Type': 'application/json',
            }
        });
        
        if (response.ok) {
            // Clear local storage
            localStorage.clear();
            
            // Clear all cookies
            document.cookie.split(";").forEach(function(c) { 
                document.cookie = c.replace(/^ +/, "").replace(/=.*/, "=;expires=" + new Date().toUTCString() + ";path=/"); 
            });
            
            // Clear session storage
            sessionStorage.clear();
            
            // Update UI to logged out state
            showLoggedOutState();
            showMessage('Logged out successfully', 'info');
        } else {
            console.error('Logout failed');
            showMessage('Logout failed. Please try again.', 'error');
        }
    } catch (error) {
        console.error('Error during logout:', error);
        showMessage('Error during logout. Please try again.', 'error');
    }
}

// Function to hide login popup
function hideLoginPopup() {
    const popup = document.getElementById('loginPopup');
    popup.classList.remove('show');
}

// Close login popup when clicking outside
document.addEventListener('click', function(event) {
    const loginArea = document.querySelector('.login-area');
    const popup = document.getElementById('loginPopup');
    
    if (!loginArea.contains(event.target)) {
        hideLoginPopup();
    }
});

// Handle postMessage from auth popup
window.addEventListener('message', function(event) {
    // Verify origin for security
    if (event.origin !== window.location.origin) {
        console.warn('Received message from unexpected origin:', event.origin);
        return;
    }

    const { type, token, error, data } = event.data;
    
    if (type === 'AUTH_SUCCESS') {
        console.log('Authentication successful:', data);
        showMessage('Authentication successful!', 'success');
        hideLoginPopup();
        // Refresh login state to update UI
        checkLoginState();
    } else if (type === 'AUTH_ERROR') {
        console.error('Authentication failed:', error, data);
        showMessage(`Authentication failed: ${error || 'Unknown error'}`, 'error');
        hideLoginPopup();
    }
});
