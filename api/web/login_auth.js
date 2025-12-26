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

// Function to toggle login popup
async function toggleLoginPopup() {
    const popup = document.getElementById('loginPopup');
    
    if (popup.classList.contains('show')) {
        popup.classList.remove('show');
    } else {
        try {
            const response = await fetch('/login');
            const html = await response.text();
            popup.innerHTML = html;
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
        
        // Store token if needed
        if (token) {
            localStorage.setItem('authToken', token);
        }
    } else if (type === 'AUTH_ERROR') {
        console.error('Authentication failed:', error, data);
        showMessage(`Authentication failed: ${error || 'Unknown error'}`, 'error');
        hideLoginPopup();
    }
});
