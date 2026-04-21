const API_BASE = window.location.origin;
let pollInterval = null;

async function startGeneration() {
    const urlInput = document.getElementById('spotify-url');
    const btn = document.getElementById('generate-btn');
    const statusSection = document.getElementById('status-section');
    const errorSection = document.getElementById('error-section');
    const resultSection = document.getElementById('result-section');
    const progressFill = document.getElementById('progress-fill');
    const statusText = document.getElementById('status-text');
    const errorText = document.getElementById('error-text');

    const spotifyUrl = urlInput.value.trim();
    if (!spotifyUrl) return;

    btn.disabled = true;
    statusSection.classList.remove('hidden');
    errorSection.classList.add('hidden');
    resultSection.classList.add('hidden');
    progressFill.style.width = '0%';
    statusText.textContent = 'starting...';

    try {
        const resp = await fetch(`${API_BASE}/api/generate`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ spotify_url: spotifyUrl }),
        });

        if (!resp.ok) {
            const data = await resp.json();
            throw new Error(data.detail || 'Failed to start generation');
        }

        const { job_id } = await resp.json();
        pollStatus(job_id);
    } catch (err) {
        errorText.textContent = err.message;
        errorSection.classList.remove('hidden');
        statusSection.classList.add('hidden');
        btn.disabled = false;
    }
}

function pollStatus(jobId) {
    const btn = document.getElementById('generate-btn');
    const statusSection = document.getElementById('status-section');
    const errorSection = document.getElementById('error-section');
    const resultSection = document.getElementById('result-section');
    const progressFill = document.getElementById('progress-fill');
    const statusText = document.getElementById('status-text');
    const errorText = document.getElementById('error-text');
    const downloadLink = document.getElementById('download-link');

    if (pollInterval) clearInterval(pollInterval);

    pollInterval = setInterval(async () => {
        try {
            const resp = await fetch(`${API_BASE}/api/status/${jobId}`);
            const job = await resp.json();

            progressFill.style.width = `${job.progress}%`;
            statusText.textContent = job.step || job.status;

            if (job.status === 'complete') {
                clearInterval(pollInterval);
                statusSection.classList.add('hidden');
                resultSection.classList.remove('hidden');
                downloadLink.href = `${API_BASE}/api/download/${jobId}`;
                btn.disabled = false;
            } else if (job.status === 'error') {
                clearInterval(pollInterval);
                statusSection.classList.add('hidden');
                errorText.textContent = job.error || 'An error occurred';
                errorSection.classList.remove('hidden');
                btn.disabled = false;
            }
        } catch (err) {
            clearInterval(pollInterval);
            errorText.textContent = 'Lost connection to server';
            errorSection.classList.remove('hidden');
            statusSection.classList.add('hidden');
            btn.disabled = false;
        }
    }, 2000);
}
