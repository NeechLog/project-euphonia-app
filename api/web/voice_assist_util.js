
// State Management
let isRecording = false;
let mediaRecorderObj;
let audioChunks = [];
let audioStream;

// UI Elements
let recordButton;
let statusText;
let responseTextElement;
let audioPlayback;
let messageBox;

// Initialize the application
function initVoiceAssist() {
    // Get UI elements
    recordButton = document.getElementById('recordButton');
    recordV0iceButton = document.getElementById('recordV0ice');
    statusText = document.getElementById('statusText');
    responseTextElement = document.getElementById('responseText');
    audioPlayback = document.getElementById('audioPlayback');
    messageBox = document.getElementById('messageBox');
    recordVoiceSection = document.getElementById('responseSection');
    // Initial check for browser support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        recordV0iceButton.disabled = true;
        statusText.textContent = "Microphone access is not supported by your browser.";
        showMessage("Your browser doesn't support microphone access. Please try a different browser.");
        return;
    }
    loadVoiceModels(document.getElementById('hashVoiceName'));
    // Add event listeners
    recordV0iceButton.addEventListener('click', toggleRecording);
    recordButton.addEventListener('click', () => {
        hideOtherSections(recordVoiceSection);
    });
}

// Toggle recording state
async function toggleRecording() {
    console.log("Toggle called" );
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showMessage("getUserMedia not supported on your browser!");
        statusText.textContent = "Microphone access not supported.";
        return;
    }

    if (isRecording) {
        stopRecording();
    } else {
        // Start the recording and destructure the result
        ({ 
            mediaRecorder: mediaRecorderObj, 
            stream: audioStream, 
            mimeType 
        } = await startRecording({
            onStart: () => {
                isRecording = true;  // Update state
                updateUIForRecording(true);
            },
            onStop: async (blob, mimeType) => {
                statusText.textContent = "Processing...";
                const wavResult = await convertAudioBlob(blob, 'wav');
                const hashVoiceName = document.getElementById('hashVoiceName').value;
                await sendAudioToServer(wavResult.blob, wavResult.fileName, hashVoiceName);
            },
            onError: (err) => handleRecordingError(err)
        }));
    }
}
/**
 * Common method to start audio recording
 * @param {Object} options - Configuration options
 * @param {string[]} [options.mimeTypes] - Array of MIME types to try (default: ['audio/webm', 'audio/ogg;codecs=opus', 'audio/wav'])
 * @param {Function} [options.onStart] - Callback when recording starts
 * @param {Function} [options.onStop] - Callback with the recorded Blob when recording stops
 * @param {Function} [options.onError] - Error callback
 * @param {Function} [options.onDataAvailable] - Callback when data is available
 * @returns {Promise<{mediaRecorder: MediaRecorder, stream: MediaStream}>} Recording objects
 */
async function startRecording(options = {}) {
    const {
        mimeTypes = ['audio/webm', 'audio/ogg;codecs=opus', 'audio/wav'],
        onStart = () => {},
        onStop = () => {},
        onError = (err) => console.error('Recording error:', err),
        onDataAvailable = () => {}
    } = options;
    console.log("Start recording called" + options);
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const selectedMimeType = mimeTypes.find(mt => MediaRecorder.isTypeSupported(mt));
        
        if (!selectedMimeType) {
            throw new Error('No supported audio format available');
        }

        const mediaRecorder = new MediaRecorder(stream, { mimeType: selectedMimeType });
        const audioChunks = [];
        console.log("mediaRecorder state", mediaRecorder.state);
        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                console.log("event.data", event.data)
                audioChunks.push(event.data);
                onDataAvailable(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            const audioBlob = new Blob(audioChunks, { type: selectedMimeType });
            stream.getTracks().forEach(track => track.stop());
            onStop(audioBlob, selectedMimeType);
        };

        mediaRecorder.onerror = (event) => {
            onError(event.error || new Error('Unknown recording error'));
        };

        mediaRecorder.start();
        onStart();
        return { mediaRecorder, stream, mimeType: selectedMimeType };

    } catch (err) {
        onError(err);
        throw err;
    }
}

// Stop audio recording
function stopRecording() {
    console.log("Stop recording called");
    if (mediaRecorderObj && mediaRecorderObj.state === "recording") {
        mediaRecorderObj.stop();
    }
    isRecording = false;
    updateUIForRecording(false);
}

// Update UI based on recording state
function updateUIForRecording(recording) {
    console.log("Update UI for recording called. Param ",recording);
    if (recording) {
        recordV0iceButton.innerHTML = `
            <img src="icons/stop-filled-icon.svg" alt="Stop" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Stop Recording`;
        recordV0iceButton.classList.remove('btn-record');
        recordV0iceButton.classList.add('btn-stop');
        statusText.textContent = "Recording... Click to stop.";
        responseTextElement.textContent = "Waiting for server...";
        audioPlayback.classList.add('hidden');
        audioPlayback.src = '';
    } else {
        recordV0iceButton.innerHTML = `
            <img src="icons/mic-icon.svg" alt="Record" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Record Voice`;
        recordV0iceButton.classList.remove('btn-stop');
        recordV0iceButton.classList.add('btn-record');

    }

}

// Send recorded audio to server
async function sendAudioToServer(audioBlob, fileName, hashVoiceName) {
    const formData = new FormData();
    //const fileName = getFileNameFromMimeType(mimeType);
    console.log(audioBlob); 
    formData.append('audio', audioBlob, fileName);
    if(hashVoiceName){
        formData.append('hashVoiceName', hashVoiceName);
    }
    statusText.textContent = "Uploading audio to server...";
    responseTextElement.textContent = "Processing...";

    try {
        const response = await fetch('/process_audio', {
            method: 'POST',
            body: formData
        });

        if (response.ok) {
            const serverText = response.headers.get('X-Response-Text');
            const audioResponseBlob = await response.blob();

            responseTextElement.textContent = serverText || "No text received from server.";
            statusText.textContent = "Processing complete! Playing audio...";
            showMessage("Successfully processed audio!", "success");

            if (audioResponseBlob.size > 0) {
                console.log("response audio" + audioResponseBlob);
                playAudioBlob(audioResponseBlob, audioPlayback, statusText);
            } else {
                statusText.textContent = "Text received, but no audio data from server.";
                showMessage("No audio received from server.", "info");
            }
        } else {
            const errorText = await response.text();
            console.error("Server Error:", response.status, errorText);
            responseTextElement.textContent = `Server Error: ${response.status}. ${errorText}`;
            statusText.textContent = "Server error.";
            showMessage(`Server Error: ${response.status}. ${errorText}`);
        }
    } catch (err) {
        console.error("Network or other error sending audio:", err);
        responseTextElement.textContent = "Network error or server unavailable. " + err.message;
        statusText.textContent = "Failed to send audio.";
        showMessage("Network error: " + err.message);
    }
}

// Helper function to get file extension from MIME type
function getFileNameFromMimeType(mimeType) {
    const extensionMap = {
        'audio/aac': 'aac',
        'audio/webm': 'webm',
        'audio/ogg': 'ogg',
        'audio/wav': 'wav',
        'audio/mp4': 'mp4'
    };
    
    const ext = Object.entries(extensionMap).find(([key, _]) => 
        mimeType.startsWith(key)
    )?.[1] || 'dat';
    
    return `recorded_audio.${ext}`;
}

// Show temporary message to user
function showMessage(message, type = 'error', duration = 3000) {
    messageBox.textContent = message;
    messageBox.className = 'message-box';
    messageBox.classList.add(type);
    messageBox.classList.add('show');

    setTimeout(() => {
        messageBox.classList.remove('show');
    }, duration);
}

// Handle recording errors
function handleRecordingError(err) {
    console.error("Error starting recording:", err);
    if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        showMessage("Microphone permission denied. Please allow microphone access in your browser settings.");
        statusText.textContent = "Microphone permission denied.";
    } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        showMessage("No microphone found. Please ensure a microphone is connected and enabled.");
        statusText.textContent = "No microphone found.";
    } else {
        showMessage("Error accessing microphone: " + err.message);
        statusText.textContent = "Could not start recording.";
    }
    isRecording = false;
}

/**
 * Play an audio blob in the specified audio element
 * @param {Blob} audioBlob - The audio blob to play
 * @param {HTMLAudioElement} audioElement - The audio element to use for playback
 * @param {HTMLElement} statusElement - Optional element to update with status messages
 */
function playAudioBlob(audioBlob, audioElement, statusElement = null) {
    if (!audioBlob || !(audioBlob instanceof Blob)) {
        const errorMsg = "Invalid audio blob provided";
        console.error(errorMsg);
        if (statusElement) {
            statusElement.textContent = errorMsg;
        }
        return Promise.reject(new Error(errorMsg));
    }

    return new Promise((resolve, reject) => {
        try {
            const audioUrl = URL.createObjectURL(audioBlob);
            audioElement.src = audioUrl;
            audioElement.classList.remove('hidden');
            
            audioElement.onloadedmetadata = () => {
                audioElement.play().then(() => {
                    if (statusElement) {
                        statusElement.textContent = "Playing audio...";
                    }
                    resolve();
                }).catch(e => {
                    const errorMsg = "Could not play audio automatically. Please use controls.";
                    console.error("Error playing audio:", e);
                    if (statusElement) {
                        statusElement.textContent = "Audio ready. Play manually.";
                    }
                    reject(e);
                });
            };
            
            audioElement.onerror = (e) => {
                const errorMsg = "Error loading audio";
                console.error(errorMsg, e);
                if (statusElement) {
                    statusElement.textContent = errorMsg;
                }
                reject(new Error(errorMsg));
            };
            
            // Clean up the object URL when done
            audioElement.onended = () => {
                URL.revokeObjectURL(audioUrl);
                if (statusElement) {
                    statusElement.textContent = "Audio playback finished";
                }
                updateUIForRecording(false);
            };
            
        } catch (e) {
            const errorMsg = `Error initializing audio playback: ${e.message}`;
            console.error(errorMsg);
            if (statusElement) {
                statusElement.textContent = errorMsg;
            }
            reject(e);
        }
    });
}

// Initialize the application when the DOM is fully loaded
document.addEventListener('DOMContentLoaded', initVoiceAssist);
