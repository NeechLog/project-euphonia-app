// JS logic for the clone voice functionality

// Clone voice UI and state
let cloneVoiceButton, cloneVoiceSection, cloneTextInput, voiceModelSelect, generateVoiceButton, clonedVoicePlayback;

// Initialize the clone voice UI
function initCloneVoiceUI() {
    cloneVoiceButton = document.getElementById('cloneVoiceButton');
    cloneVoiceSection = document.getElementById('cloneVoiceSection');
    cloneTextInput = document.getElementById('cloneTextInput');
    voiceModelSelect = document.getElementById('voiceModelSelect');
    generateVoiceButton = document.getElementById('generateVoiceButton');
    clonedVoicePlayback = document.getElementById('clonedVoicePlayback');

    // Toggle clone voice section visibility
    cloneVoiceButton.addEventListener('click', () => {

        loadVoiceModels(voiceModelSelect);
        hideOtherSections(cloneVoiceSection);
    });

    // Handle generate voice button click
    generateVoiceButton.addEventListener('click', generateClonedVoice);
}

// Load available voice models from cache or server
// Function moved to hashutils.js

// Generate cloned voice based on the input text and selected model
async function generateClonedVoice() {
    const text = cloneTextInput.value.trim();
    const modelId = voiceModelSelect.value;
    
    if (!text) {
        showMessage('Please enter text to clone', 'error');
        return;
    }
    
    if (!modelId) {
        showMessage('Please select a voice model', 'error');
        return;
    }
    
    try {
        // Show loading state
        generateVoiceButton.disabled = true;
        generateVoiceButton.innerHTML = `
            <span class="inline-block animate-spin mr-2">
                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
            </span>
            Generating...
        `;
        
        // Prepare form data
        const formData = new FormData();
        formData.append('phrase', text);
        formData.append('hash_id', modelId);
        
        // Send request to generate voice
        const response = await fetch('/gendia', {
            method: 'POST',
            body: formData
        });
        
        if (!response.ok) {
            throw new Error(`Server responded with status: ${response.status}`);
        }
        
        // Get the audio blob
        const audioBlob = await response.blob();
        
        // Play the generated audio using playAudioBlob
        try {
            await playAudioBlob(audioBlob, clonedVoicePlayback);
            showMessage('Voice generated and played successfully!', 'success');
        } catch (error) {
            console.error('Error playing audio:', error);
            showMessage('Error playing audio: ' + error.message, 'error');
        }
        
    } catch (error) {
        console.error('Error generating voice:', error);
        showMessage('Failed to generate voice: ' + error.message, 'error');
    } finally {
        // Reset button state
        generateVoiceButton.disabled = false;
        generateVoiceButton.innerHTML = `
            <img src="icons/generate-icon.svg" alt="Generate" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Generate Voice
        `;
    }
}

// Initialize when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', initCloneVoiceUI);
