// ffmpeg-conversion-lib-st.js

// Ensure FFmpeg and fetchFile are available globally from the CDN scripts.
// FOR SINGLE-THREADED VERSION, USE @ffmpeg/core:
// e.g., <script src="https://unpkg.com/@ffmpeg/core@0.12.6/dist/umd/ffmpeg-core.js"></script>
//       <script src="https://unpkg.com/@ffmpeg/ffmpeg@0.12.10/dist/umd/ffmpeg.js"></script>

let ffmpegInstance;
let isFFmpegLoading = false;
let isFFmpegLoaded = false;

/**
 * Initializes and loads the FFmpeg instance (single-threaded).
 * @param {function} statusCallback - Function to call with status updates (string).
 * @param {function} logCallback - Function to call with FFmpeg log messages ({type, message}).
 * @returns {Promise<boolean>} True if loaded successfully, false otherwise.
 */
async function loadFFmpeg(statusCallback = console.log, logCallback = console.log) {
    if (isFFmpegLoaded) {
        statusCallback("FFmpeg is already loaded.");
        return true;
    }
    if (isFFmpegLoading) {
        statusCallback("FFmpeg is currently loading. Please wait.");
        return false; 
    }

    if (typeof FFmpeg === 'undefined' || typeof FFmpeg.FFmpeg === 'undefined') {
        statusCallback("Error: FFmpeg library not found. Ensure CDN scripts (@ffmpeg/core and @ffmpeg/ffmpeg) are loaded before this script.");
        console.error("FFmpeg object not found. Make sure @ffmpeg/core and @ffmpeg/ffmpeg are loaded.");
        return false;
    }

    isFFmpegLoading = true;
    const { FFmpeg: FFmpegClass } = FFmpeg; // Destructure from the global FFmpeg object
    ffmpegInstance = new FFmpegClass();

    ffmpegInstance.on('log', ({ type, message }) => {
        logCallback({ type, message });
    });

    try {
        statusCallback("Loading FFmpeg (Single-Threaded), please wait... (this may take a moment)");
        await ffmpegInstance.load();
        isFFmpegLoaded = true;
        isFFmpegLoading = false;
        statusCallback("FFmpeg (Single-Threaded) loaded successfully.");
        return true;
    } catch (error) {
        console.error("Error loading FFmpeg (ST):", error);
        statusCallback(`Error loading FFmpeg (ST): ${error.message}. Check console.`);
        isFFmpegLoading = false;
        return false;
    }
}

/**
 * Converts an audio file to the specified output format using FFmpeg.
 * @param {File} inputFile - The audio file (e.g., a WebM File object).
 * @param {string} outputFormat - The desired output format ('mp3' or 'wav').
 * @param {function} statusCallback - Function to call with status updates (string).
 * @param {function} logCallback - Function to call with FFmpeg log messages ({type, message}).
 * @returns {Promise<{blob: Blob, fileName: string, logs: string[]}|null>} Object with blob and filename, or null on error.
 */
async function convertAudio(inputFile, outputFormat, statusCallback = console.log, logCallback = console.log) {
    if (!isFFmpegLoaded || !ffmpegInstance) {
        statusCallback("FFmpeg is not loaded. Please load it first using loadFFmpeg().");
        return null;
    }
    if (!inputFile) {
        statusCallback("No input file provided for conversion.");
        return null;
    }
    if (outputFormat !== 'mp3' && outputFormat !== 'wav') {
        statusCallback("Invalid output format. Please choose 'mp3' or 'wav'.");
        return null;
    }

    const inputFileName = `input.${inputFile.name.split('.').pop() || 'webm'}`;
    const outputFileName = `output.${outputFormat}`;
    const mimeType = outputFormat === 'mp3' ? 'audio/mpeg' : 'audio/wav';
    let localLogs = [];

    const tempLogCallback = ({ type, message }) => {
        localLogs.push(`[${type}] ${message}`);
        logCallback({ type, message });
    };

    const originalLogger = ffmpegInstance.logger;
    ffmpegInstance.setLogger(tempLogCallback);

    statusCallback(`Starting conversion to ${outputFormat.toUpperCase()} (ST)...`);

    try {
        statusCallback("Writing input file to FFmpeg's virtual file system...");
        await ffmpegInstance.writeFile(inputFileName, await FFmpeg.fetchFile(inputFile));
        statusCallback("Input file written. Executing FFmpeg command...");

        let command = ['-i', inputFileName];
        if (outputFormat === 'mp3') {
            command.push('-acodec', 'libmp3lame', '-b:a', '192k', '-ar', '44100', '-ac', '2', outputFileName);
        } else { // wav
            command.push(outputFileName);
        }

        await ffmpegInstance.exec(command);
        statusCallback("FFmpeg command executed. Reading output file...");

        const data = await ffmpegInstance.readFile(outputFileName);
        statusCallback("Output file read. Creating Blob...");

        const blob = new Blob([data.buffer], { type: mimeType });
        
        statusCallback(`Conversion to ${outputFormat.toUpperCase()} (ST) successful!`);
        return {
            blob: blob,
            fileName: `converted_audio.${outputFormat}`,
            logs: localLogs
        };

    } catch (error) {
        console.error(`Error during ${outputFormat} (ST) conversion:`, error);
        statusCallback(`Error converting to ${outputFormat} (ST): ${error.message}. Check console and FFmpeg logs.`);
        localLogs.push(`[ERROR] Conversion failed: ${error.message}`);
        return {
            blob: null,
            fileName: null,
            logs: localLogs,
            error: error.message
        };
    } finally {
        ffmpegInstance.setLogger(originalLogger);
        try {
            if (await ffmpegInstance.pathExists(inputFileName)) {
                await ffmpegInstance.deleteFile(inputFileName);
            }
            if (await ffmpegInstance.pathExists(outputFileName)) {
                await ffmpegInstance.deleteFile(outputFileName);
            }
        } catch (cleanupError) {
            console.warn("Error during FFmpeg (ST) filesystem cleanup:", cleanupError);
        }
    }
}

// --- Example Usage (Illustrative - adapt to your UI logic) ---
/*
async function handleFileConversionST(file, format) {
    const statusDisplay = document.getElementById('statusDisplay'); 
    const ffmpegLogDisplay = document.getElementById('ffmpegLogDisplay'); 

    const updateStatus = (msg) => { if(statusDisplay) statusDisplay.textContent = msg; console.log(msg); };
    const updateLogs = (log) => {
        if(ffmpegLogDisplay) ffmpegLogDisplay.textContent += log.message + '\n';
        console.log(`FFmpeg Log [${log.type}]: ${log.message}`);
    };

    if (!isFFmpegLoaded && !isFFmpegLoading) {
        await loadFFmpeg(updateStatus, updateLogs);
    } else if (isFFmpegLoading) {
        updateStatus("FFmpeg (ST) is still loading, please wait...");
        return;
    }

    if (!isFFmpegLoaded) {
        updateStatus("FFmpeg (ST) could not be loaded. Cannot convert.");
        return;
    }

    if (ffmpegLogDisplay) ffmpegLogDisplay.textContent = ''; 
    updateStatus(`Converting ${file.name} to ${format} using ST FFmpeg...`);

    const result = await convertAudio(file, format, updateStatus, updateLogs);

    if (result && result.blob) {
        updateStatus(`ST Conversion successful: ${result.fileName}`);
        
        const url = URL.createObjectURL(result.blob);
        // const audioPlayer = document.getElementById('audioPlayer'); 
        // if (audioPlayer) {
        //     audioPlayer.src = url;
        //     audioPlayer.hidden = false;
        //     audioPlayer.load();
        // }

        // const downloadLink = document.getElementById('downloadLink'); 
        // if (downloadLink) {
        //     downloadLink.href = url;
        //     downloadLink.download = result.fileName;
        //     downloadLink.textContent = `Download ${result.fileName}`;
        //     downloadLink.hidden = false;
        // }
        console.log("ST Converted File URL:", url);

    } else {
        updateStatus(`ST Conversion failed. ${result ? result.error || '' : ''}`);
        console.error("ST Conversion failed. Logs:", result ? result.logs : "No result object");
    }
}

// --- Setup Example (in your main script or HTML) ---
// window.onload = async () => {
//     const statusDisplay = (msg) => console.log('Initial Load Status (ST):', msg);
//     const logDisplay = (log) => console.log('Initial Load Log (ST):', log.message);
//     await loadFFmpeg(statusDisplay, logDisplay);

//     // document.getElementById('convertButtonST').onclick = () => {
//     //     const file = document.getElementById('fileInput').files[0];
//     //     const format = 'mp3'; 
//     //     if (file) {
//     //         handleFileConversionST(file, format);
//     //     } else {
//     //         alert("Please select a file first!");
//     //     }
//     // };
// };
*/

