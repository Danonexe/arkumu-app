/**
 * Upload Form Handler with Chunked Upload Support
 * 
 * Handles the upload form with automatic chunking for large file uploads.
 * Integrates with the existing streaming upload system.
 */
class UploadFormHandler {
    constructor() {
        this.selectedFiles = [];
        this.currentUploader = null;
        this.isUploading = false;
        
        this.initializeElements();
        this.bindEvents();
    }

    initializeElements() {
        // Form elements
        this.form = document.getElementById('streaming-upload-form');
        this.fileInput = document.getElementById('file-input');
        this.folderModeCheckbox = document.getElementById('folder-mode');
        this.baseFolderSelect = document.getElementById('base-folder');
        this.organizationInput = document.getElementById('organization');
        this.uploadButton = document.getElementById('upload-button');
        
        // Progress elements
        this.progressContainer = document.getElementById('upload-progress');
        this.progressText = document.getElementById('progress-text');
        this.progressPercentage = document.getElementById('progress-percentage');
        this.progressBar = document.getElementById('progress-bar');
        
        // Status and results elements
        this.statusContainer = document.getElementById('upload-status');
        this.resultsContainer = document.getElementById('upload-results');
        this.selectedFilesInfo = document.getElementById('selected-files-info');
        this.fileCountSpan = document.getElementById('file-count');
        this.totalSizeSpan = document.getElementById('total-size');
        
        // Results elements
        this.resultFilesCount = document.getElementById('result-files-count');
        this.resultTotalSize = document.getElementById('result-total-size');
        this.resultDuration = document.getElementById('result-duration');
    }

    bindEvents() {
        // Folder mode toggle
        if (this.folderModeCheckbox) {
            this.folderModeCheckbox.addEventListener('change', (e) => {
                this.handleFolderModeChange(e.target.checked);
            });
        }

        // File selection
        if (this.fileInput) {
            this.fileInput.addEventListener('change', (e) => {
                this.handleFileSelection(e.target.files);
            });
        }

        // Upload button
        if (this.uploadButton) {
            this.uploadButton.addEventListener('click', (e) => {
                e.preventDefault();
                this.handleUploadClick();
            });
        }
    }

    handleFolderModeChange(isFolderMode) {
        const helpText = this.fileInput.nextElementSibling;
        
        if (isFolderMode) {
            this.fileInput.setAttribute('webkitdirectory', '');
            this.fileInput.setAttribute('directory', '');
            helpText.textContent = 'Select a folder to preserve its structure';
        } else {
            this.fileInput.removeAttribute('webkitdirectory');
            this.fileInput.removeAttribute('directory');
            helpText.textContent = 'You can select multiple files at once';
        }
        
        // Clear current selection when switching modes
        this.fileInput.value = '';
        this.selectedFiles = [];
        this.updateFileSelectionDisplay();
    }

    handleFileSelection(files) {
        console.log('Files selected:', files.length);
        
        if (files.length > 0) {
            this.selectedFiles = Array.from(files);
            this.updateFileSelectionDisplay();
        }
    }

    updateFileSelectionDisplay() {
        if (this.selectedFiles.length === 0) {
            this.selectedFilesInfo.classList.add('hidden');
            return;
        }

        const totalSize = this.selectedFiles.reduce((sum, file) => sum + file.size, 0);
        
        this.selectedFilesInfo.classList.remove('hidden');
        this.fileCountSpan.textContent = `${this.selectedFiles.length} files selected`;
        this.totalSizeSpan.textContent = formatFileSize(totalSize);
        
        // Show chunking info if many files
        if (this.selectedFiles.length > 100) {
            const chunks = Math.ceil(this.selectedFiles.length / 75);
            this.fileCountSpan.textContent += ` (${chunks} chunks)`;
        }
    }

    async handleUploadClick() {
        if (this.isUploading) {
            // Cancel current upload
            if (this.currentUploader) {
                this.currentUploader.cancelUpload();
            }
            return;
        }

        // Validate form
        const validation = this.validateForm();
        if (!validation.valid) {
            this.showError(validation.message);
            return;
        }

        // Start upload
        await this.startUpload();
    }

    validateForm() {
        if (this.selectedFiles.length === 0) {
            return { valid: false, message: 'Please select files to upload' };
        }

        if (this.baseFolderSelect && !this.baseFolderSelect.value) {
            return { valid: false, message: 'Please select a base folder' };
        }

        return { valid: true };
    }

    async startUpload() {
        try {
            this.isUploading = true;
            this.updateUploadButton(true);
            this.hideResults();
            this.clearStatus();

            // Get form values
            const baseFolder = this.baseFolderSelect ? this.baseFolderSelect.value : '';
            const organization = this.organizationInput ? this.organizationInput.value : '';
            
            // Check if we're in folder mode
            const isFolderMode = this.folderModeCheckbox && this.folderModeCheckbox.checked;
            
            // For folder mode, we need to preserve individual file paths
            let folderName = '';
            if (isFolderMode && this.selectedFiles.length > 0) {
                // Extract the root folder name for display purposes only
                const firstFile = this.selectedFiles[0];
                if (firstFile.webkitRelativePath) {
                    const pathParts = firstFile.webkitRelativePath.split('/');
                    folderName = pathParts[0]; // Just for logging/display
                }
            }

            // Determine if we need chunking
            const useChunking = this.selectedFiles.length > 75; // Chunk if more than 75 files
            
            if (useChunking) {
                console.log(`🔄 Using chunked upload for ${this.selectedFiles.length} files`);
                await this.performChunkedUpload(folderName, organization, baseFolder, isFolderMode);
            } else {
                console.log(`📤 Using standard upload for ${this.selectedFiles.length} files`);
                await this.performStandardUpload(folderName, organization, baseFolder, isFolderMode);
            }

        } catch (error) {
            console.error('Upload error:', error);
            this.showError(error.message || 'Upload failed');
        } finally {
            this.isUploading = false;
            this.updateUploadButton(false);
        }
    }

    async performChunkedUpload(folderName, organization, baseFolder, isFolderMode) {
        this.currentUploader = new ChunkedUploadHandler({
            chunkSize: 75,
            maxConcurrent: 3,
            preserveFolderStructure: isFolderMode,
            onProgress: (progress) => this.updateProgress(progress),
            onChunkComplete: (chunk, result) => this.handleChunkComplete(chunk, result),
            onComplete: (summary) => this.handleUploadComplete(summary),
            onError: (error, chunk) => this.handleUploadError(error, chunk)
        });

        this.showProgress();
        
        const result = await this.currentUploader.uploadFiles(
            this.selectedFiles,
            folderName,
            organization,
            baseFolder
        );

        return result;
    }

    async performStandardUpload(folderName, organization, baseFolder, isFolderMode) {
        this.showProgress();
        
        // Use existing streaming upload
        const formData = new FormData();
        
        // For folder mode, we don't set a single folder_name
        // Instead, we let the backend handle individual file paths
        if (!isFolderMode) {
            // Create the final folder path for non-folder mode
            let finalFolderName = folderName;
            if (baseFolder) {
                finalFolderName = baseFolder + (folderName ? '/' + folderName : '');
            }
            formData.append('folder_name', finalFolderName);
        } else {
            // For folder mode, set the base folder only
            formData.append('folder_name', baseFolder || '');
            formData.append('preserve_folder_structure', 'true');
        }
        
        if (organization) {
            formData.append('organization', organization);
        }

        this.selectedFiles.forEach(file => {
            formData.append('files', file);
        });

        // Add CSRF token
        const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]');
        if (csrfToken) {
            formData.append('csrfmiddlewaretoken', csrfToken.value);
        }

        try {
            const response = await fetch('/storage/upload/streaming/', {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error(`HTTP ${response.status}: ${response.statusText}`);
            }

            const result = await response.json();
            
            if (result.success) {
                this.handleUploadComplete(result);
            } else {
                throw new Error(result.error || 'Upload failed');
            }

        } catch (error) {
            this.handleUploadError(error);
        }
    }

    updateProgress(progress) {
        if (!this.progressContainer) return;

        this.progressContainer.classList.remove('hidden');
        
        // Update progress bar
        if (this.progressBar) {
            this.progressBar.value = progress.percentage;
        }
        
        if (this.progressPercentage) {
            this.progressPercentage.textContent = `${progress.percentage}%`;
        }
        
        if (this.progressText) {
            let text = `Uploading ${progress.processedFiles}/${progress.totalFiles} files`;
            
            if (progress.estimatedRemaining) {
                text += ` (${formatDuration(progress.estimatedRemaining)} remaining)`;
            }
            
            this.progressText.textContent = text;
        }
    }

    handleChunkComplete(chunk, result) {
        console.log(`Chunk ${chunk.index + 1} completed:`, result);
        
        // Could add per-chunk status updates here
        this.showStatus(`Completed chunk ${chunk.index + 1}`, 'info');
    }

    handleUploadComplete(summary) {
        console.log('Upload completed:', summary);
        
        this.hideProgress();
        
        if (summary.success) {
            this.showStatus('Upload completed successfully!', 'success');
            this.showResults(summary);
        } else {
            const message = summary.cancelled 
                ? 'Upload was cancelled' 
                : `Upload completed with ${summary.failedFiles} failed files`;
            this.showStatus(message, summary.cancelled ? 'info' : 'warning');
            this.showResults(summary);
        }
    }

    handleUploadError(error, chunk) {
        console.error('Upload error:', error);
        
        this.hideProgress();
        
        let message = 'Upload failed: ' + (error.message || 'Unknown error');
        if (chunk) {
            message += ` (Chunk ${chunk.index + 1})`;
        }
        
        this.showError(message);
    }

    showProgress() {
        if (this.progressContainer) {
            this.progressContainer.classList.remove('hidden');
        }
    }

    hideProgress() {
        if (this.progressContainer) {
            this.progressContainer.classList.add('hidden');
        }
    }

    showStatus(message, type = 'info') {
        if (!this.statusContainer) return;

        const alertClass = {
            'success': 'alert-success',
            'error': 'alert-error',
            'warning': 'alert-warning',
            'info': 'alert-info'
        }[type] || 'alert-info';

        this.statusContainer.innerHTML = `
            <div class="alert ${alertClass}">
                <span>${message}</span>
            </div>
        `;
    }

    showError(message) {
        this.showStatus(message, 'error');
    }

    clearStatus() {
        if (this.statusContainer) {
            this.statusContainer.innerHTML = '';
        }
    }

    showResults(summary) {
        if (!this.resultsContainer) return;

        this.resultsContainer.classList.remove('hidden');
        
        if (this.resultFilesCount) {
            this.resultFilesCount.textContent = summary.completedFiles || 0;
        }
        
        if (this.resultTotalSize) {
            // Calculate total size from uploaded files
            const totalSize = this.selectedFiles
                .slice(0, summary.completedFiles)
                .reduce((sum, file) => sum + file.size, 0);
            this.resultTotalSize.textContent = formatFileSize(totalSize);
        }
        
        if (this.resultDuration) {
            this.resultDuration.textContent = formatDuration(summary.duration || 0);
        }
    }

    hideResults() {
        if (this.resultsContainer) {
            this.resultsContainer.classList.add('hidden');
        }
    }

    updateUploadButton(isUploading) {
        if (!this.uploadButton) return;

        if (isUploading) {
            this.uploadButton.textContent = 'Cancel Upload';
            this.uploadButton.classList.remove('btn-primary');
            this.uploadButton.classList.add('btn-error');
        } else {
            this.uploadButton.textContent = 'Upload Files';
            this.uploadButton.classList.remove('btn-error');
            this.uploadButton.classList.add('btn-primary');
        }
    }
}

// Initialize when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Only initialize on upload form pages
    if (document.getElementById('streaming-upload-form')) {
        window.uploadFormHandler = new UploadFormHandler();
        console.log('📁 Upload form handler initialized');
    }
}); 