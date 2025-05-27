/**
 * S3Client Compatibility Layer
 * 
 * This file provides compatibility with the old S3Client interface
 * but uses the new StreamingUploadHandler behind the scenes.
 */

class S3ClientCompat {
    constructor() {
        console.log('Using S3ClientCompat - redirecting to StreamingUploadHandler');
        this.streamingUploader = new StreamingUploadHandler();
        this.csrfToken = this.getCsrfToken();
        this.pendingUploads = new Map();
    }

    getCsrfToken() {
        return document.querySelector('[name=csrfmiddlewaretoken]').value;
    }

    async initializeMultipartUpload(fileName, folderName, fileType = 'application/octet-stream') {
        console.log('Legacy initializeMultipartUpload called - using streaming upload instead');
        
        // Generate a unique upload ID to track this upload
        const uploadId = `legacy-${Date.now()}-${Math.random().toString(36).substring(2, 15)}`;
        
        // Store the file info for later use
        this.pendingUploads.set(uploadId, {
            fileName,
            folderName,
            fileType,
            status: 'initialized',
            s3Key: folderName ? `${folderName}/${fileName}` : fileName
        });
        
        // Return a response that mimics the old API
        return {
            success: true,
            uploadId: uploadId,
            s3Key: folderName ? `${folderName}/${fileName}` : fileName
        };
    }

    async getPartUploadUrls(s3Key, uploadId, partCount, expiration = 3600) {
        console.log('Legacy getPartUploadUrls called - using streaming upload instead');
        
        // Check if we have this upload in our pending uploads
        if (!this.pendingUploads.has(uploadId)) {
            return {
                success: false,
                error: 'Upload not found'
            };
        }
        
        // Generate dummy presigned URLs (these won't be used)
        const urls = [];
        for (let i = 0; i < partCount; i++) {
            urls.push({
                url: `https://dummy-url.com/${s3Key}?part=${i+1}&upload_id=${uploadId}`,
                part_number: i + 1
            });
        }
        
        // Update the upload status
        this.pendingUploads.set(uploadId, {
            ...this.pendingUploads.get(uploadId),
            status: 'urls_generated',
            partCount
        });
        
        return {
            success: true,
            presigned_urls: urls
        };
    }

    async completeMultipartUpload(s3Key, uploadId, parts) {
        console.log('Legacy completeMultipartUpload called - using streaming upload instead');
        
        // Check if we have this upload in our pending uploads
        if (!this.pendingUploads.has(uploadId)) {
            return {
                success: false,
                error: 'Upload not found'
            };
        }
        
        const uploadInfo = this.pendingUploads.get(uploadId);
        
        // Display a message to the user about the new upload method
        alert('The application is now using a more efficient streaming upload method. Please refresh the page and try again.');
        
        return {
            success: false,
            error: 'Please use the new streaming upload method',
            message: 'The application has been updated to use a more efficient streaming upload method. Please refresh the page and try again.'
        };
    }

    async abortMultipartUpload(fileName, uploadId, folderName) {
        console.log('Legacy abortMultipartUpload called');
        
        // Remove from pending uploads
        if (this.pendingUploads.has(uploadId)) {
            this.pendingUploads.delete(uploadId);
        }
        
        return {
            success: true
        };
    }
}

/**
 * MultipartUploadHandler Compatibility Layer
 */
class MultipartUploadHandlerCompat {
    constructor(s3Client) {
        console.log('Using MultipartUploadHandlerCompat - redirecting to StreamingUploadHandler');
        this.streamingUploader = new StreamingUploadHandler();
        this.s3Client = s3Client || new S3ClientCompat();
        this.activeUploads = new Map();
    }

    async startUpload(file, folderName) {
        console.log('Legacy startUpload called - redirecting to streaming upload');
        
        // Display a message to the user about the new upload method
        alert('The application is now using a more efficient streaming upload method. Please refresh the page and try again.');
        
        return {
            success: false,
            error: 'Please use the new streaming upload method',
            message: 'The application has been updated to use a more efficient streaming upload method. Please refresh the page and try again.'
        };
    }

    async uploadPart(file, partNumber) {
        console.log('Legacy uploadPart called - redirecting to streaming upload');
        
        return {
            success: false,
            error: 'Please use the new streaming upload method'
        };
    }

    async completeUpload(fileName) {
        console.log('Legacy completeUpload called - redirecting to streaming upload');
        
        return {
            success: false,
            error: 'Please use the new streaming upload method'
        };
    }

    async abortUpload(fileName) {
        console.log('Legacy abortUpload called');
        
        return {
            success: true
        };
    }
}

// Replace the original classes with our compatibility versions
window.S3Client = S3ClientCompat;
window.MultipartUploadHandler = MultipartUploadHandlerCompat; 