/**
 * Streaming Upload Handler
 * Manages the streaming upload process for files of all sizes
 */
class StreamingUploadHandler {
    constructor() {
        this.csrfToken = this.getCsrfToken();
        this.activeUploads = new Map();
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }

    /**
     * Upload a single file using the streaming upload endpoint
     * @param {File} file - The file to upload
     * @param {string} folderName - The folder to upload to
     * @param {function} onProgress - Progress callback function
     * @param {function} onSuccess - Success callback function
     * @param {function} onError - Error callback function
     */
    async uploadFile(file, folderName, onProgress, onSuccess, onError) {
        try {
            console.log(`Starting streaming upload for ${file.name} to folder ${folderName}`);
            
            // Create a unique ID for this upload
            const uploadId = `${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
            
            // Store upload info
            this.activeUploads.set(uploadId, {
                file,
                folderName,
                status: 'uploading'
            });
            
            // Create form data
            const formData = new FormData();
            formData.append('folder_name', folderName);
            formData.append('file', file);
            
            // Add CSRF token
            formData.append('csrfmiddlewaretoken', this.csrfToken);
            
            // Create upload request with progress tracking
            const xhr = new XMLHttpRequest();
            xhr.upload.addEventListener('progress', (event) => {
                if (event.lengthComputable) {
                    const percentComplete = (event.loaded / event.total) * 100;
                    
                    if (onProgress) {
                        onProgress({
                            percent: Math.round(percentComplete),
                            loaded: event.loaded,
                            total: event.total
                        });
                    }
                    
                    console.log(`Upload progress for ${file.name}: ${Math.round(percentComplete)}%`);
                }
            });
            
            // Set up completion handler
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        
                        if (response.success) {
                            console.log(`Upload completed for ${file.name}`);
                            this.activeUploads.set(uploadId, {
                                ...this.activeUploads.get(uploadId),
                                status: 'completed'
                            });
                            
                            if (onSuccess) {
                                onSuccess(response);
                            }
                        } else {
                            console.error(`Upload failed for ${file.name}: ${response.error}`);
                            this.activeUploads.set(uploadId, {
                                ...this.activeUploads.get(uploadId),
                                status: 'failed',
                                error: response.error
                            });
                            
                            if (onError) {
                                onError(response);
                            }
                        }
                    } catch (error) {
                        console.error(`Error parsing response for ${file.name}: ${error}`);
                        
                        if (onError) {
                            onError({
                                success: false,
                                error: 'Failed to parse server response'
                            });
                        }
                    }
                } else {
                    console.error(`Upload failed for ${file.name} with status ${xhr.status}`);
                    
                    if (onError) {
                        onError({
                            success: false,
                            error: `Server returned status ${xhr.status}`
                        });
                    }
                }
            };
            
            // Set up error handler
            xhr.onerror = () => {
                console.error(`Network error during upload of ${file.name}`);
                
                this.activeUploads.set(uploadId, {
                    ...this.activeUploads.get(uploadId),
                    status: 'failed',
                    error: 'Network error'
                });
                
                if (onError) {
                    onError({
                        success: false,
                        error: 'Network error during upload'
                    });
                }
            };
            
            // Send the request
            xhr.open('POST', '/storage/upload/single/', true);
            xhr.send(formData);
            
            return uploadId;
        } catch (error) {
            console.error(`Error starting upload for ${file.name}: ${error}`);
            
            if (onError) {
                onError({
                    success: false,
                    error: error.message || 'Unknown error'
                });
            }
            
            throw error;
        }
    }

    /**
     * Upload multiple files using the batch streaming upload endpoint
     * @param {Array<File>} files - The files to upload
     * @param {string} folderName - The folder to upload to
     * @param {function} onProgress - Progress callback function
     * @param {function} onSuccess - Success callback function
     * @param {function} onError - Error callback function
     */
    async uploadFiles(files, folderName, onProgress, onSuccess, onError) {
        try {
            console.log(`Starting batch upload of ${files.length} files to folder ${folderName}`);
            
            // Create a unique ID for this batch upload
            const batchId = `batch-${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
            
            // Store batch info
            this.activeUploads.set(batchId, {
                files,
                folderName,
                status: 'uploading'
            });
            
            // Create form data
            const formData = new FormData();
            formData.append('folder_name', folderName);
            
            // Add all files
            for (let i = 0; i < files.length; i++) {
                formData.append('files', files[i]);
            }
            
            // Add CSRF token
            formData.append('csrfmiddlewaretoken', this.csrfToken);
            
            // Create upload request with progress tracking
            const xhr = new XMLHttpRequest();
            xhr.upload.addEventListener('progress', (event) => {
                if (event.lengthComputable) {
                    const percentComplete = (event.loaded / event.total) * 100;
                    
                    if (onProgress) {
                        onProgress({
                            percent: Math.round(percentComplete),
                            loaded: event.loaded,
                            total: event.total
                        });
                    }
                    
                    console.log(`Batch upload progress: ${Math.round(percentComplete)}%`);
                }
            });
            
            // Set up completion handler
            xhr.onload = () => {
                if (xhr.status >= 200 && xhr.status < 300) {
                    try {
                        const response = JSON.parse(xhr.responseText);
                        
                        if (response.success) {
                            console.log(`Batch upload completed: ${response.total_uploaded} files`);
                            this.activeUploads.set(batchId, {
                                ...this.activeUploads.get(batchId),
                                status: 'completed'
                            });
                            
                            if (onSuccess) {
                                onSuccess(response);
                            }
                        } else {
                            console.error(`Batch upload failed: ${response.error}`);
                            this.activeUploads.set(batchId, {
                                ...this.activeUploads.get(batchId),
                                status: 'failed',
                                error: response.error
                            });
                            
                            if (onError) {
                                onError(response);
                            }
                        }
                    } catch (error) {
                        console.error(`Error parsing batch upload response: ${error}`);
                        
                        if (onError) {
                            onError({
                                success: false,
                                error: 'Failed to parse server response'
                            });
                        }
                    }
                } else {
                    console.error(`Batch upload failed with status ${xhr.status}`);
                    
                    if (onError) {
                        onError({
                            success: false,
                            error: `Server returned status ${xhr.status}`
                        });
                    }
                }
            };
            
            // Set up error handler
            xhr.onerror = () => {
                console.error(`Network error during batch upload`);
                
                this.activeUploads.set(batchId, {
                    ...this.activeUploads.get(batchId),
                    status: 'failed',
                    error: 'Network error'
                });
                
                if (onError) {
                    onError({
                        success: false,
                        error: 'Network error during upload'
                    });
                }
            };
            
            // Send the request
            xhr.open('POST', '/storage/upload/api/', true);
            xhr.send(formData);
            
            return batchId;
        } catch (error) {
            console.error(`Error starting batch upload: ${error}`);
            
            if (onError) {
                onError({
                    success: false,
                    error: error.message || 'Unknown error'
                });
            }
            
            throw error;
        }
    }

    /**
     * Cancel an active upload
     * @param {string} uploadId - The ID of the upload to cancel
     */
    cancelUpload(uploadId) {
        // Note: This is a client-side cancellation only
        // The upload may continue on the server if it's already in progress
        
        const upload = this.activeUploads.get(uploadId);
        if (upload) {
            console.log(`Cancelling upload ${uploadId}`);
            this.activeUploads.set(uploadId, {
                ...upload,
                status: 'cancelled'
            });
        }
        
        // In a real implementation, we would also abort the XHR request
        // This would require storing the XHR object in the activeUploads map
    }
}

// Make globally available for browser
window.StreamingUploadHandler = StreamingUploadHandler; 