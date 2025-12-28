// Cache configuration
const CACHE_TTL = 2.5 * 60 * 60 * 1000; // 2.5 hours in milliseconds
const VOICE_MODELS_CACHE_KEY = 'voiceModelsCache';

// Cache utility functions
const cache = {
    // Get item from cache if it exists and isn't expired
    get: (key) => {
        const item = sessionStorage.getItem(key);
        if (!item) return null;
        
        const { value, expiry } = JSON.parse(item);
        if (Date.now() > expiry) {
            sessionStorage.removeItem(key);
            return null;
        }
        return value;
    },
    
    // Set item in cache with TTL
    set: (key, value, ttl = CACHE_TTL) => {
        const item = {
            value,
            expiry: Date.now() + ttl
        };
        sessionStorage.setItem(key, JSON.stringify(item));
    },
    
    // Remove item from cache
    remove: (key) => {
        sessionStorage.removeItem(key);
    }
}

/**
 * Adds a voice model name to the cache
 * @param {string} modelName - The name of the voice model to add
 * @param {number} [ttl] - Optional TTL in milliseconds (defaults to CACHE_TTL)
 * @returns {boolean} - True if the model was added, false otherwise
 */
function addVoiceModelToCache(modelName, ttl = CACHE_TTL) {
    if (!modelName) {
        console.error('No model name provided');
        return false;
    }
    
    try {
        // Get existing models from cache
        let models = cache.get(VOICE_MODELS_CACHE_KEY) || [];
        
        // Add the new model if it doesn't already exist
        if (!models.includes(modelName)) {
            models.push(modelName);
            // Update cache with the new list
            cache.set(VOICE_MODELS_CACHE_KEY, models, ttl);
            console.log(`Added voice model '${modelName}' to cache`);
            return true;
        } else {
            console.log(`Voice model '${modelName}' already exists in cache`);
            return false;
        }
    } catch (error) {
        console.error('Error adding voice model to cache:', error);
        return false;
    }
};

/**
 * Updates a select dropdown with voice model options
 * @param {string[]} models - Array of voice model names
 * @param {HTMLSelectElement} selectWidget - The select element to update
 */
function updateVoiceModelSelect(models, selectWidget) {
    if (!selectWidget) {
        console.error('No select widget provided');
        return;
    }
    
    // Clear existing options except the first one
    while (selectWidget.options.length > 1) {
        selectWidget.remove(1);
    }
    
    // Add new model options
    models.forEach(model => {
        const option = document.createElement('option');
        option.value = model;
        option.textContent = model.toLowerCase();
        selectWidget.appendChild(option);
    });
}

/**
 * Load available voice models from cache or server
 * @param {HTMLSelectElement} selectWidget - The select element to update with voice models
 */
async function loadVoiceModels(selectWidget) {
    try {
        // Try to get from cache first
        const cachedModels = cache.get(VOICE_MODELS_CACHE_KEY);
        if (cachedModels) {
            console.log('Using cached voice models');
            updateVoiceModelSelect(cachedModels, selectWidget);
            return;
        }
        
        // If not in cache, fetch from server
        const response = await fetch('/get_voice_models');
        if (!response.ok) {
            throw new Error('Failed to load voice models');
        }
        const response_json = await response.json();
        console.log("Status on server List is "+ response_json.status);
        const models = response_json.voice_models;
        
        // Cache the response only if user is authenticated
        if (sessionStorage.getItem('authenticated') === 'true') {
            cache.set(VOICE_MODELS_CACHE_KEY, models);
        }
        
        // Update the UI
        updateVoiceModelSelect(models, selectWidget);
    } catch (error) {
        console.error('Error loading voice models:', error);
        showMessage('Failed to load voice models: ' + error.message);
        
        // If there's an error, try to use cached data if available
        const cachedModels = cache.get(VOICE_MODELS_CACHE_KEY);
        if (cachedModels) {
            console.log('Falling back to cached voice models');
            updateVoiceModelSelect(cachedModels, selectWidget);
        }
    }
}
function hideOtherSections(functionSection) {
    let responseSection, cloneVoiceSection, trainin_modelSection;
    responseSection = document.getElementById("responseSection")
    cloneVoiceSection = document.getElementById("cloneVoiceSection")
    trainin_modelSection = document.getElementById("trainin_model")

    if(functionSection == responseSection){
        cloneVoiceSection.classList.add("hidden");
        trainin_modelSection.classList.add("hidden");
    }
    if(functionSection == cloneVoiceSection){
        responseSection.classList.add("hidden");
        trainin_modelSection.classList.add("hidden");
    }
    if(functionSection == trainin_modelSection){
        responseSection.classList.add("hidden");
        cloneVoiceSection.classList.add("hidden");
    }
    functionSection.classList.remove("hidden")
} 