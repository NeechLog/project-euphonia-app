// audio-conversion-functions.js

/**
 * @typedef {Object} ConversionResult
 * @property {Blob | null} blob - The resulting audio Blob, or null on error.
 * @property {string | null} fileName - The suggested filename for the Blob, or null on error.
 * @property {string | null} error - An error message if conversion failed.
 */

/**
 * Converts an input audio Blob to WAV or MP3 format.
 *
 * @param {Blob} inputAudioBlob - The audio Blob to convert (e.g., from MediaRecorder).
 * @param {'wav' | 'mp3'} outputFormat - The desired output format.
 * @param {object} [options] - Optional parameters.
 * @param {function(string): void} [options.statusCallback] - Callback for status updates.
 * @param {number} [options.mp3BitRate=128] - Bitrate for MP3 encoding (e.g., 128, 192, 256).
 * @returns {Promise<ConversionResult>} A promise that resolves with the conversion result.
 */
async function convertAudioBlob(inputAudioBlob, outputFormat, options = {}) {
    const { statusCallback = () => {}, mp3BitRate = 128 } = options;

    if (!(inputAudioBlob instanceof Blob)) {
        return { blob: null, fileName: null, error: "Invalid input: inputAudioBlob must be a Blob." };
    }
    if (outputFormat !== 'wav' && outputFormat !== 'mp3') {
        return { blob: null, fileName: null, error: "Invalid outputFormat. Choose 'wav' or 'mp3'." };
    }
    if (outputFormat === 'mp3' && typeof lamejs === 'undefined') {
        statusCallback("Error: lamejs library is not loaded. MP3 conversion is not possible.");
        console.error("lamejs is not defined. Please include it for MP3 encoding.");
        return { blob: null, fileName: null, error: "lamejs library not loaded for MP3 conversion." };
    }

    let audioBuffer;
    try {
        statusCallback("Decoding input audio...");
        const arrayBuffer = await inputAudioBlob.arrayBuffer();
        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
        audioBuffer = await audioContext.decodeAudioData(arrayBuffer);
        statusCallback("Audio decoded successfully.");
    } catch (err) {
        console.error("Error decoding audio data:", err);
        statusCallback(`Error decoding audio: ${err.message}`);
        return { blob: null, fileName: null, error: `Failed to decode audio: ${err.message}` };
    }

    try {
        let resultBlob;
        let outputFileName = `converted_audio.${outputFormat}`; // Basic filename

        if (outputFormat === 'wav') {
            statusCallback("Converting to WAV...");
            resultBlob = audioBufferToWav(audioBuffer);
            statusCallback("WAV conversion complete.");
        } else if (outputFormat === 'mp3') {
            statusCallback("Converting to MP3 (this may take a moment)...");
            resultBlob = audioBufferToMp3(audioBuffer, mp3BitRate, (progressMsg) => {
                statusCallback(`MP3 Encoding: ${progressMsg}`);
            });
            statusCallback("MP3 conversion complete.");
        }
        
        return { blob: resultBlob, fileName: outputFileName, error: null };

    } catch (err) {
        console.error(`Error during ${outputFormat} conversion:`, err);
        statusCallback(`Error converting to ${outputFormat}: ${err.message}`);
        return { blob: null, fileName: null, error: `Conversion to ${outputFormat} failed: ${err.message}` };
    }
}

/**
 * Converts an AudioBuffer to a WAV Blob.
 * (This function is a direct adaptation from the previous example)
 * @param {AudioBuffer} aBuffer - The AudioBuffer to convert.
 * @returns {Blob} A Blob containing the WAV audio data.
 */
function audioBufferToWav(aBuffer) {
    const numOfChan = aBuffer.numberOfChannels;
    const L = aBuffer.length * numOfChan * 2 + 44; // Total length of buffer
    const buffer = new ArrayBuffer(L);
    const view = new DataView(buffer);
    let pos = 0;

    function writeString(s) {
        for (let i = 0; i < s.length; i++) {
            view.setUint8(pos++, s.charCodeAt(i));
        }
    }

    writeString('RIFF');
    view.setUint32(pos, L - 8, true); pos += 4;
    writeString('WAVE');
    writeString('fmt ');
    view.setUint32(pos, 16, true); pos += 4;
    view.setUint16(pos, 1, true); pos += 2;
    view.setUint16(pos, numOfChan, true); pos += 2;
    view.setUint32(pos, aBuffer.sampleRate, true); pos += 4;
    view.setUint32(pos, aBuffer.sampleRate * numOfChan * 2, true); pos += 4;
    view.setUint16(pos, numOfChan * 2, true); pos += 2;
    view.setUint16(pos, 16, true); pos += 2;
    writeString('data');
    view.setUint32(pos, L - pos - 4, true); pos += 4;

    const channels = [];
    for (let i = 0; i < numOfChan; i++) {
        channels.push(aBuffer.getChannelData(i));
    }

    for (let i = 0; i < aBuffer.length; i++) {
        for (let chan = 0; chan < numOfChan; chan++) {
            let sample = channels[chan][i];
            sample = Math.max(-1, Math.min(1, sample));
            sample = sample < 0 ? sample * 0x8000 : sample * 0x7FFF;
            view.setInt16(pos, sample, true);
            pos += 2;
        }
    }
    return new Blob([buffer], { type: 'audio/wav' });
}

/**
 * Converts an AudioBuffer to an MP3 Blob using lamejs.
 * (This function is a direct adaptation from the previous example)
 * @param {AudioBuffer} aBuffer - The AudioBuffer to convert.
 * @param {number} [bitRate=128] - The desired MP3 bitrate (e.g., 128, 192).
 * @param {function(string): void} [progressCallback] - Callback for encoding progress messages.
 * @returns {Blob} A Blob containing the MP3 audio data.
 */
function audioBufferToMp3(aBuffer, bitRate = 128, progressCallback = () => {}) {
    if (typeof lamejs === 'undefined') {
        throw new Error("lamejs library is not loaded. Cannot convert to MP3.");
    }
    const mp3Encoder = new lamejs.Mp3Encoder(aBuffer.numberOfChannels, aBuffer.sampleRate, bitRate);
    
    const pcmSamples = [];
    for (let i = 0; i < aBuffer.numberOfChannels; i++) {
        pcmSamples.push(float32ToInt16(aBuffer.getChannelData(i)));
    }

    const dataBuffer = [];
    const bufferSize = 1152; // LAME standard MP3 frame size
    let encodedSamples = 0;
    const totalSamples = pcmSamples[0].length;

    progressCallback("0%");

    for (let i = 0; i < totalSamples; i += bufferSize) {
        const leftChunk = pcmSamples[0].subarray(i, i + bufferSize);
        const rightChunk = (aBuffer.numberOfChannels === 2) ? pcmSamples[1].subarray(i, i + bufferSize) : null;
        
        const mp3buf = mp3Encoder.encodeBuffer(leftChunk, rightChunk);
        if (mp3buf.length > 0) {
            dataBuffer.push(new Uint8Array(mp3buf));
        }
        encodedSamples += leftChunk.length;
        // Update progress less frequently to avoid too many callbacks
        if (i % (bufferSize * 20) === 0 || i + bufferSize >= totalSamples) {
            progressCallback(`${((encodedSamples / totalSamples) * 100).toFixed(0)}%`);
        }
    }

    const mp3buf = mp3Encoder.flush();
    if (mp3buf.length > 0) {
        dataBuffer.push(new Uint8Array(mp3buf));
    }
    progressCallback("100%");
    return new Blob(dataBuffer, { type: 'audio/mpeg' });
}

/**
 * Helper function to convert Float32 PCM data to Int16 PCM data.
 * @param {Float32Array} buffer - The Float32Array to convert.
 * @returns {Int16Array} The converted Int16Array.
 */
function float32ToInt16(buffer) {
    let l = buffer.length;
    const buf = new Int16Array(l);
    while (l--) {
        // Clamp values to [-1.0, 1.0] before scaling to 16-bit range
        const s = Math.max(-1, Math.min(1, buffer[l]));
        buf[l] = s < 0 ? s * 0x8000 : s * 0x7FFF;
    }
    return buf;
}

// --- Example Usage (Illustrative) ---
/*
async function exampleUsage(mediaRecorderBlob) {
    console.log("Starting conversion from MediaRecorder Blob...");

    const statusUpdate = (message) => {
        console.log("Status:", message);
        // Update your UI here, e.g., document.getElementById('status').textContent = message;
    };

    // Convert to WAV
    const wavResult = await convertAudioBlob(mediaRecorderBlob, 'wav', { statusCallback: statusUpdate });
    if (wavResult.blob) {
        console.log("WAV Conversion successful:", wavResult.fileName);
        // Create a download link or play the WAV blob
        // const wavUrl = URL.createObjectURL(wavResult.blob);
        // console.log("WAV URL:", wavUrl);
    } else {
        console.error("WAV Conversion failed:", wavResult.error);
    }

    console.log("---");

    // Convert to MP3 (ensure lamejs is loaded on your page: <script src="https://cdn.jsdelivr.net/npm/lamejs@1.2.1/lame.min.js"></script>)
    if (typeof lamejs !== 'undefined') {
        const mp3Result = await convertAudioBlob(mediaRecorderBlob, 'mp3', {
            statusCallback: statusUpdate,
            mp3BitRate: 192 // Optional: set bitrate
        });
        if (mp3Result.blob) {
            console.log("MP3 Conversion successful:", mp3Result.fileName);
            // const mp3Url = URL.createObjectURL(mp3Result.blob);
            // console.log("MP3 URL:", mp3Url);
        } else {
            console.error("MP3 Conversion failed:", mp3Result.error);
        }
    } else {
        console.warn("lamejs not loaded, skipping MP3 conversion example.");
    }
}

// To test with a MediaRecorder blob:
// 1. Record audio using MediaRecorder.
// 2. In the 'dataavailable' event, get the blob: event.data
// 3. Call: exampleUsage(event.data);
*/

