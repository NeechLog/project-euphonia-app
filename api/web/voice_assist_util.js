// Configuration
const SERVER_URL = window.location.origin+ "/process_audio";
console.log("SERVER_URL: ", SERVER_URL);

// State Management
let isRecording = false;
let mediaRecorder;
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
    statusText = document.getElementById('statusText');
    responseTextElement = document.getElementById('responseText');
    audioPlayback = document.getElementById('audioPlayback');
    messageBox = document.getElementById('messageBox');

    // Initial check for browser support
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        recordButton.disabled = true;
        statusText.textContent = "Microphone access is not supported by your browser.";
        showMessage("Your browser doesn't support microphone access. Please try a different browser.");
        return;
    }

    // Add event listeners
    recordButton.addEventListener('click', toggleRecording);
}

// Toggle recording state
async function toggleRecording() {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        showMessage("getUserMedia not supported on your browser!");
        statusText.textContent = "Microphone access not supported.";
        return;
    }

    if (isRecording) {
        stopRecording();
    } else {
        await startRecording();
    }
}

// Start audio recording
async function startRecording() {
    try {
        audioStream = await navigator.mediaDevices.getUserMedia({ audio: true });
        statusText.textContent = "Microphone access granted. Initializing recorder...";
//TODO: Need to move these mimetypes and mimetypes with extensions defined in getExtendedMap to 1 place. Then use getExtendedMap to get the mimetypes as well as extensions.
        const mimeTypes = [
            'audio/aac',
            'audio/webm;codecs=opus',
            'audio/ogg;codecs=opus',
            'audio/wav',
            'audio/mp4'
        ];
        
        const selectedMimeType = mimeTypes.find(mt => MediaRecorder.isTypeSupported(mt));
        
        if (!selectedMimeType) {
            showMessage("No suitable audio format supported by the browser for recording.");
            statusText.textContent = "Recording format not supported.";
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
            }
            return;
        }

        mediaRecorder = new MediaRecorder(audioStream, { mimeType: selectedMimeType });
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = async () => {
            statusText.textContent = "Recording stopped. Processing audio...";
            const audioBlob = new Blob(audioChunks, { type: selectedMimeType });
            
            if (audioBlob.size === 0) {
                showMessage("Recorded audio is empty. Please try again.");
                statusText.textContent = "Recording was empty.";
                return;
            }
           // playAudioBlob(audioBlob, audioPlayback, "testing raw audio");
            statusText.textContent = "Converting the webm to wavip d";
            wavAudioResult = await convertAudioBlob(audioBlob, 'wav');
            //playAudioBlob(wavAudioResult.blob, audioPlayback, "testing wav audio"); 
            await sendAudioToServer(wavAudioResult.blob, wavAudioResult.fileName);
            
            if (audioStream) {
                audioStream.getTracks().forEach(track => track.stop());
            }
        };

        mediaRecorder.start();
        isRecording = true;
        updateUIForRecording(true);

    } catch (err) {
        handleRecordingError(err);
    }
}

// Stop audio recording
function stopRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
    }
    isRecording = false;
    updateUIForRecording(false);
}

// Update UI based on recording state
function updateUIForRecording(recording) {
    if (recording) {
        recordButton.innerHTML = `
            <img src="icons/stop-filled-icon.svg" alt="Stop" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Stop Recording`;
        recordButton.classList.remove('btn-record');
        recordButton.classList.add('btn-stop');
        statusText.textContent = "Recording... Click to stop.";
    } else {
        recordButton.innerHTML = `
            <img src="icons/mic-icon.svg" alt="Record" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Record Voice`;
        recordButton.classList.remove('btn-stop');
        recordButton.classList.add('btn-record');
    }
    responseTextElement.textContent = "Waiting for server...";
    audioPlayback.classList.add('hidden');
    audioPlayback.src = '';
}

// Send recorded audio to server
async function sendAudioToServer(audioBlob, fileName) {
    const formData = new FormData();
    //const fileName = getFileNameFromMimeType(mimeType);
    console.log(audioBlob); 
    formData.append('audio', audioBlob, fileName);

    statusText.textContent = "Uploading audio to server...";
    responseTextElement.textContent = "Processing...";

    try {
        const response = await fetch(SERVER_URL, {
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
