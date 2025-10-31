// JS logic for the new training model UI and audio logic
// This file is loaded after voice_assist_util.js in HTML

// Training model UI and state
let trainModelButton, trainModelDiv, trainTextInput, trainHashInput,trainRecordButton, trainReplayButton, trainSubmitButton, trainAudioPlayback;
let isTrainRecording = false;
let trainMediaRecorder;
let trainAudioChunks = [];
let trainAudioBlob = null;
let trainAudioStream;

function initTrainModelUI() {
    trainModelButton = document.getElementById('trainModelButton');
    trainModelDiv = document.getElementById('trainin_model');
    trainTextInput = document.getElementById('trainTextInput');
    trainHashInput = document.getElementById('trainHashInput');
    trainRecordButton = document.getElementById('trainRecordButton');
    trainReplayButton = document.getElementById('trainReplayButton');
    trainSubmitButton = document.getElementById('trainSubmitButton');
    trainAudioPlayback = document.getElementById('trainAudioPlayback');

    trainModelButton.addEventListener('click', () => {
        hideOtherSections(trainModelDiv);
        loadVoiceModels(document.getElementById('hashNameInput'));
    });
    trainRecordButton.addEventListener('click', toggleTrainRecording);
    trainReplayButton.addEventListener('click', replayTrainAudio);
    trainSubmitButton.addEventListener('click', submitTrainData);
}

async function toggleTrainRecording() {
    if (isTrainRecording) {
        stopTrainRecording();
    } else {
        ({
            mediaRecorder: trainMediaRecorder,
            stream: trainAudioStream,
            mimeType

        } = await startRecording({
                onStart: () => {
                    isTrainRecording = true;
                    trainRecordButton.innerHTML = `
            <img src="icons/mic-icon.svg" alt="Record" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Stop Recording`;
                    trainRecordButton.classList.remove('btn-stop');
                    trainRecordButton.classList.add('btn-record');
                },
                onStop: (blob, mimeType) => {
                    trainAudioBlob = blob;
                    trainAudioPlayback.src = URL.createObjectURL(blob);
                    trainAudioPlayback.classList.remove('hidden');
                },
                onError: (err) => alert('Recording error: ' + err.message)
            })
        );
    }
}


function stopTrainRecording() {
    if (trainMediaRecorder && trainMediaRecorder.state === 'recording') {
        trainMediaRecorder.stop();
    }
    isTrainRecording = false;
    trainRecordButton.innerHTML = `
            <img src="icons/mic-icon.svg" alt="Record" class="inline-block mr-2 align-text-bottom" width="20" height="20">
            Record Voice`;
    trainRecordButton.classList.remove('btn-stop');
    trainRecordButton.classList.add('btn-record');
}

function replayTrainAudio() {
    if (trainAudioBlob) {
        trainAudioPlayback.src = URL.createObjectURL(trainAudioBlob);
        trainAudioPlayback.classList.remove('hidden');
        trainAudioPlayback.play();
    } else {
        alert('No training audio recorded yet!');
    }
}

async function submitTrainData() {
    if (!trainAudioBlob) {
        alert('Please record training audio first!');
        return;
    }
    const text = trainTextInput.value.trim();
    if (!text) {
        alert('Please enter training text!');
        return;
    }
    const hashName = trainHashInput.value.trim();
    if (!hashName) {
        alert('Going ahead with default hash');
        
    } 
    // Convert to WAV using the same util as main app
    if (typeof convertAudioBlob === 'function') {
        const wavResult = await convertAudioBlob(trainAudioBlob, 'wav');
        if (!wavResult || !wavResult.blob) {
            alert('Audio conversion failed!');
            return;
        }
        sendTrainAudioToServer(wavResult.blob, wavResult.fileName, text, hashName);
    } else {
        // fallback: send webm
        sendTrainAudioToServer(trainAudioBlob, 'train_audio.webm', text,hashName);
    }
}

async function sendTrainAudioToServer(audioBlob, fileName, text, hashName) {
    const formData = new FormData();
    formData.append('audio', audioBlob, fileName);
    formData.append('text', text);
    if(hashName) {
        formData.append('hash_id',hashName);
    }
    try {
        const response = await fetch('/train_audio', {
            method: 'POST',
            body: formData
        });
        if (response.ok) {
            //alert('Training data submitted successfully!');
            trainModelDiv.classList.add('hidden');
            trainModelButton.disabled = false;
            trainTextInput.value = '';
            trainAudioBlob = null;
            trainAudioPlayback.classList.add('hidden');
            addVoiceModelToCache(hashName)
        } else {
            alert('Failed to submit training data.');
        }
    } catch (err) {
        alert('Error submitting training data: ' + err.message);
    }
}

document.addEventListener('DOMContentLoaded', initTrainModelUI);
