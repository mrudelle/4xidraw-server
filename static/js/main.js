const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('file-input');
const pageSizeSelect = document.getElementById('page-size');
const customPageSizeInput = document.getElementById('custom-page-size');
const form = document.getElementById('plot-form');
const successMessage = document.getElementById('success-message');

// Show custom page size input if "Custom" is selected
pageSizeSelect.addEventListener('change', () => {
    if (pageSizeSelect.value === 'Custom') {
        customPageSizeInput.classList.remove('hidden');
    } else {
        customPageSizeInput.classList.add('hidden');
    }
});

// Handle drag-and-drop file upload
dropArea.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropArea.classList.add('bg-gray-200');
});

dropArea.addEventListener('dragleave', () => {
    dropArea.classList.remove('bg-gray-200');
});

dropArea.addEventListener('drop', (e) => {
    e.preventDefault();
    dropArea.classList.remove('bg-gray-200');
    const files = e.dataTransfer.files;
    if (files.length > 0) {
        fileInput.files = files;
        fileInput.dispatchEvent(new Event('change')); // Trigger change event
    }
});

dropArea.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', () => {
    if (fileInput.files.length > 0) {
        dropArea.querySelector('p').textContent = fileInput.files[0].name;
    }
});

// Handle form submission
form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const formData = new FormData();
    const file = fileInput.files[0];
    const pageSize = pageSizeSelect.value === 'Custom' ? customPageSizeInput.value.trim() : pageSizeSelect.value;

    if (!file) {
        alert('Please provide a file.');
        return;
    }

    if (!pageSize || (pageSizeSelect.value === 'Custom' && !customPageSizeInput.value.trim())) {
        alert('Please provide a valid page size.');
        return;
    }

    formData.append('file', file);
    formData.append('page_size', pageSize);

    try {
        const response = await fetch('/plot', {
            method: 'POST',
            body: formData,
        });

        if (response.ok) {
            successMessage.classList.remove('hidden');
            form.classList.add('hidden');
        } else {
            const error = await response.json();
            alert(`Error: ${error.message}`);
        }
    } catch (err) {
        alert('An error occurred while uploading the file.');
    }
});
