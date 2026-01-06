// File Upload Component
window.fileUpload = function(config) {
    return {
        // Configuration
        multiple: config.multiple || false,
        isPatient: config.isPatient || false,
        uploadUrl: config.uploadUrl || window.location.href,
        csrfToken: config.csrfToken,
        accept: config.accept || '.csv,.txt',
        acceptText: config.acceptText || 'CSV or TXT files only',
        showFileNames: config.showFileNames || false,

        // Single file state
        file: null,
        filename: '',
        fileSize: '',
        uploading: false,
        uploaded: false,
        uploadProgress: 0,
        uploadStatus: '',

        // Multiple files state
        files: [],
        fileCounter: 0,

        // Track Quill editor instances
        quillEditors: {},

        // Validation error state
        validationError: null,
        validationErrors: [],
        validationWarnings: [],
        validationMetadata: null,
        suggestPrecheck: false,
        precheckUrl: null,

        init() {
            if (this.multiple) {
                // Initialize with one empty upload field
                this.addUploadField();
            }
        },

        // Multiple file methods
        addUploadField() {
            this.fileCounter++;
            this.files.push({
                id: this.fileCounter,
                name: '',
                comments: '',
                file: null,
                filename: '',
                fileSize: '',
                uploading: false,
                uploaded: false,
                uploadProgress: 0,
                uploadStatus: ''
            });
        },

        removeUploadField(index) {
            if (this.files.length > 1) {
                const fileId = this.files[index].id;

                // Clean up Quill editor instance if it exists
                const editorId = `quill-editor-${fileId}`;
                if (window.fileUploadQuillEditors && window.fileUploadQuillEditors[editorId]) {
                    delete window.fileUploadQuillEditors[editorId];
                }

                this.files.splice(index, 1);
            }
        },

        handleFileSelect(event, index) {
            const file = event.target.files[0];
            if (file && this.files[index]) {
                this.files[index].file = file;
                this.files[index].filename = file.name;
                this.files[index].fileSize = this.formatFileSize(file.size);
            }
        },

        removeFile(index) {
            if (this.files[index]) {
                const fileId = this.files[index].id;
                this.files[index].file = null;
                this.files[index].filename = '';
                this.files[index].fileSize = '';
                this.files[index].uploading = false;
                this.files[index].uploaded = false;
                this.files[index].uploadProgress = 0;
                this.files[index].uploadStatus = '';
                this.files[index].comments = '';

                // Clear the input
                const input = document.getElementById('file-upload-' + fileId);
                if (input) input.value = '';

                // Clear the Quill editor if it exists
                const editorId = `quill-editor-${fileId}`;
                if (window.fileUploadQuillEditors && window.fileUploadQuillEditors[editorId]) {
                    window.fileUploadQuillEditors[editorId].setText('');
                }
            }
        },

        getReadyCount() {
            return this.files.filter(f => f.file && !f.uploaded).length;
        },

        // Single file methods
        handleSingleFileSelect(event) {
            const file = event.target.files[0];
            if (file) {
                this.file = file;
                this.filename = file.name;
                this.fileSize = this.formatFileSize(file.size);

                // Auto-upload if configured
                if (window.autoUpload) {
                    this.uploadSingleFile();
                }
            }
        },

        removeSingleFile() {
            this.file = null;
            this.filename = '';
            this.fileSize = '';
            this.uploading = false;
            this.uploaded = false;
            this.uploadProgress = 0;
            this.uploadStatus = '';

            // Clear the input
            const input = document.getElementById('single-file-upload');
            if (input) input.value = '';
        },

        uploadAllFiles() {
            // Upload all files that have been selected
            const readyFiles = this.files.filter(f => f.file && !f.uploaded && !f.uploading);

            if (readyFiles.length === 0) {
                alert('Please select files to upload');
                return;
            }

            // Upload each file
            readyFiles.forEach((fileObj) => {
                // Find the actual index of this file in the files array
                const actualIndex = this.files.indexOf(fileObj);
                this.uploadFile(fileObj, actualIndex);
            });
        },

        uploadFile(fileObj, index) {
            if (!fileObj.file) return;

            // Show overlay with filename
            window.uploadOverlay.show(fileObj.file.name);

            fileObj.uploading = true;
            fileObj.uploadProgress = 0;
            fileObj.uploadStatus = 'Uploading...';

            const formData = new FormData();
            formData.append('file', fileObj.file);
            formData.append('csrfmiddlewaretoken', this.csrfToken);

            // Add file metadata if provided
            if (fileObj.name) {
                formData.append('file_name', fileObj.name);
            }

            // Add comments if provided
            if (fileObj.comments) {
                formData.append('file_comments', fileObj.comments);
            }

            const xhr = new XMLHttpRequest();

            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    const progress = Math.round((event.loaded / event.total) * 100);
                    fileObj.uploadProgress = progress;
                    fileObj.uploadStatus = `Uploading... ${progress}%`;
                    // Update overlay progress
                    window.uploadOverlay.updateProgress(progress);
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    const data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        fileObj.uploaded = true;
                        fileObj.uploading = false;
                        fileObj.uploadStatus = 'Upload complete';
                        fileObj.uploadProgress = 100;

                        // Dispatch success event
                        this.$dispatch('file-uploaded', {
                            fileId: data.file_id,
                            auditId: data.audit_id, // Include audit ID if returned
                            index: index
                        });

                        // If an audit was started, begin polling for its status
                        if (data.audit_id) {
                            if (window.pollExistingAuditStatus) {
                                window.pollExistingAuditStatus(data.audit_id);
                            } else {
                                console.warn('pollExistingAuditStatus function not found');
                            }
                        } else {
                            console.warn('No audit_id in response');
                        }

                        // Transition overlay to processing state
                        window.uploadOverlay.setProcessing();

                        // Check if all files are uploaded (for multiple mode)
                        if (this.multiple) {
                            const allUploaded = this.files.every(f => !f.file || f.uploaded);
                            if (allUploaded) {
                                // Reload page after all files are uploaded
                                const reloadDelay = 3000; // 3 seconds always
                                setTimeout(() => {
                                    window.location.reload();
                                }, reloadDelay);
                            }
                        } else {
                            // For single file mode, reload page
                            const reloadDelay = 3000; // 3 seconds always
                            setTimeout(() => {
                                window.location.reload();
                            }, reloadDelay);
                        }
                    } else {
                        window.uploadOverlay.hide();
                        fileObj.uploading = false;
                        fileObj.uploadStatus = 'Upload failed';
                        alert(data.error || 'Upload failed');
                    }
                } else {
                    window.uploadOverlay.hide();
                    fileObj.uploading = false;
                    fileObj.uploadStatus = 'Upload failed';

                    // Try to parse error response
                    let errorMessage = 'Upload failed';
                    try {
                        const errorData = JSON.parse(xhr.responseText);
                        if (errorData.validation_errors && errorData.validation_errors.length > 0) {
                            // Show detailed validation errors
                            this.showValidationError(errorData, fileObj);
                            return; // Don't show alert
                        } else if (errorData.error) {
                            errorMessage = errorData.error;
                        }
                    } catch (e) {
                        // Could not parse error, use generic message
                    }
                    alert(errorMessage);
                }
            };

            xhr.onerror = () => {
                window.uploadOverlay.hide();
                fileObj.uploading = false;
                fileObj.uploadStatus = 'Upload failed';
                alert('Upload failed due to network error');
            };

            xhr.ontimeout = () => {
                window.uploadOverlay.hide();
                fileObj.uploading = false;
                fileObj.uploadStatus = 'Upload timed out - processing may continue in background';
                alert('Upload timed out, but processing may be continuing in the background. Please refresh the page in a few minutes to check status.');
            };

            xhr.open('POST', this.uploadUrl);
            xhr.timeout = 300000; // 5 minute timeout
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        },

        uploadSingleFile() {
            if (!this.file) return;

            // Show overlay with filename
            window.uploadOverlay.show(this.file.name);

            this.uploading = true;
            this.uploadProgress = 0;
            this.uploadStatus = 'Uploading...';

            const formData = new FormData();
            formData.append('file', this.file);
            formData.append('csrfmiddlewaretoken', this.csrfToken);

            // Check for debug submission checkbox
            const debugCheckbox = document.getElementById('debug-submission');
            if (debugCheckbox && debugCheckbox.checked) {
                formData.append('debug_submission', 'true');
            }

            const xhr = new XMLHttpRequest();

            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    const progress = Math.round((event.loaded / event.total) * 100);
                    this.uploadProgress = progress;
                    this.uploadStatus = `Uploading... ${progress}%`;
                    // Update overlay progress
                    window.uploadOverlay.updateProgress(progress);
                }
            };

            xhr.onload = () => {
                if (xhr.status === 200) {
                    const data = JSON.parse(xhr.responseText);
                    if (data.success) {
                        this.uploaded = true;
                        this.uploading = false;
                        this.uploadStatus = 'Upload complete';
                        this.uploadProgress = 100;

                        // Transition overlay to processing state
                        window.uploadOverlay.setProcessing();

                        this.$dispatch('file-uploaded', {
                            fileId: data.file_id,
                            auditId: data.audit_id // Include audit ID if returned
                        });

                        // If an audit was started, begin polling for its status
                        if (data.audit_id && window.pollExistingAuditStatus) {
                            window.pollExistingAuditStatus(data.audit_id);
                        }

                        // Set flag and reload to show processing status
                        sessionStorage.setItem('naaccord_check_processing', 'true');
                        setTimeout(() => {
                            window.location.reload();
                        }, 1000);
                    } else {
                        window.uploadOverlay.hide();
                        this.uploading = false;
                        this.uploadStatus = 'Upload failed';

                        // Show detailed validation errors if available
                        if (data.validation_errors && data.validation_errors.length > 0) {
                            this.showValidationError(data);
                        } else {
                            alert(data.error || 'Upload failed');
                        }
                    }
                } else {
                    window.uploadOverlay.hide();
                    this.uploading = false;
                    this.uploadStatus = 'Upload failed';

                    // Try to parse error response
                    let errorMessage = 'Upload failed';
                    try {
                        const errorData = JSON.parse(xhr.responseText);
                        if (errorData.validation_errors && errorData.validation_errors.length > 0) {
                            this.showValidationError(errorData);
                            return; // Don't show alert
                        } else if (errorData.error) {
                            errorMessage = errorData.error;
                        }
                    } catch (e) {
                        // Could not parse error, use generic message
                    }
                    alert(errorMessage);
                }
            };

            xhr.onerror = () => {
                window.uploadOverlay.hide();
                this.uploading = false;
                this.uploadStatus = 'Upload failed';
                alert('Upload failed due to network error');
            };

            xhr.ontimeout = () => {
                window.uploadOverlay.hide();
                this.uploading = false;
                this.uploadStatus = 'Upload timed out - processing may continue in background';
                alert('Upload timed out, but processing may be continuing in the background. Please refresh the page in a few minutes to check status.');
            };

            xhr.open('POST', this.uploadUrl);
            xhr.timeout = 300000; // 5 minute timeout
            xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
            xhr.send(formData);
        },

// Utility methods
        formatFileSize(bytes) {
            if (bytes === 0) return '0 Bytes';
            const k = 1024;
            const sizes = ['Bytes', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
        },

        showValidationError(errorData, fileObj) {
            // Store validation error details
            this.validationError = errorData.error || 'File validation failed';
            this.validationErrors = errorData.validation_errors || [];
            this.validationWarnings = errorData.validation_warnings || [];
            this.validationMetadata = errorData.metadata || null;
            this.suggestPrecheck = errorData.suggest_precheck || false;
            this.precheckUrl = errorData.precheck_url || null;

            // Clear the file selection for retry
            if (fileObj) {
                // Multiple file mode
                fileObj.file = null;
                fileObj.filename = '';
            } else {
                // Single file mode
                this.file = null;
                this.filename = '';
            }

            // Scroll to error display
            this.$nextTick(() => {
                const errorEl = document.getElementById('validation-error-display');
                if (errorEl) {
                    errorEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
                }
            });
        },

        clearValidationError() {
            this.validationError = null;
            this.validationErrors = [];
            this.validationWarnings = [];
            this.validationMetadata = null;
            this.suggestPrecheck = false;
            this.precheckUrl = null;
        }
    };
}

// Global upload overlay management
window.uploadOverlay = {
    overlay: null,
    progressBar: null,
    statusText: null,
    messageText: null,

    show(filename) {
        // Create full-page overlay
        this.overlay = document.createElement('div');
        this.overlay.id = 'page-upload-overlay';
        this.overlay.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(255, 255, 255, 0.95);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            z-index: 9999;
            backdrop-filter: blur(2px);
        `;

        this.overlay.innerHTML = `
            <div style="text-align: center; max-width: 500px;">
                <div style="margin-bottom: 20px;">
                    <svg class="h-12 w-12 text-blue-600" style="display: inline-block;" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                    </svg>
                </div>
                <h2 id="upload-status-title" style="font-size: 1.25rem; font-weight: 600; color: #1f2937; margin-bottom: 8px;">Uploading File</h2>
                <p id="upload-filename" style="color: #6b7280; font-size: 0.875rem; margin-bottom: 16px; word-break: break-all;">
                    ${filename || 'file'}
                </p>

                <!-- Progress bar -->
                <div style="width: 100%; margin: 20px 0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                        <span id="upload-status-text" style="color: #4b5563; font-size: 0.875rem;">Uploading...</span>
                        <span id="upload-progress-text" style="color: #4b5563; font-size: 0.875rem;">0%</span>
                    </div>
                    <div style="width: 100%; height: 8px; background: #e5e7eb; border-radius: 9999px; overflow: hidden;">
                        <div id="upload-progress-bar" style="height: 100%; background: #3b82f6; width: 0%; transition: width 0.3s ease; border-radius: 9999px;"></div>
                    </div>
                </div>

                <p id="upload-message" style="color: #9ca3af; font-size: 0.75rem; margin-top: 8px;">
                    Please wait, do not close this page...
                </p>
            </div>
        `;

        document.body.appendChild(this.overlay);

        // Store references to elements we'll update
        this.progressBar = document.getElementById('upload-progress-bar');
        this.progressText = document.getElementById('upload-progress-text');
        this.statusText = document.getElementById('upload-status-text');
        this.statusTitle = document.getElementById('upload-status-title');
        this.messageText = document.getElementById('upload-message');

        // Disable all interactions
        document.body.style.overflow = 'hidden';
    },

    updateProgress(percent) {
        if (this.progressBar) {
            this.progressBar.style.width = percent + '%';
            this.progressText.textContent = percent + '%';
        }
    },

    setProcessing() {
        if (this.statusTitle) {
            this.statusTitle.textContent = 'Processing Upload';
            this.statusText.textContent = 'Upload complete';
            this.progressText.textContent = '100%';
            this.progressBar.style.width = '100%';
            this.messageText.textContent = 'Preparing to refresh page...';

            // Change icon to spinner
            const iconContainer = this.overlay.querySelector('svg').parentElement;
            iconContainer.innerHTML = `
                <svg class="animate-spin h-12 w-12 text-blue-600" style="display: inline-block; animation: spin 1s linear infinite;" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                    <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                    <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                </svg>
            `;

            // Add spinner animation if not already present
            if (!document.querySelector('#spinner-animation-style')) {
                const style = document.createElement('style');
                style.id = 'spinner-animation-style';
                style.textContent = `
                    @keyframes spin {
                        from { transform: rotate(0deg); }
                        to { transform: rotate(360deg); }
                    }
                `;
                document.head.appendChild(style);
            }
        }
    },

    hide() {
        if (this.overlay) {
            this.overlay.remove();
            document.body.style.overflow = '';
            this.overlay = null;
        }
    }
}

// Initialize Quill editor for file comments
window.initializeQuillEditor = function(fileId) {
    // Check if Quill is available
    if (typeof Quill === 'undefined') {
        console.warn('Quill not loaded, falling back to textarea');
        return;
    }

    const editorId = `quill-editor-${fileId}`;
    const textareaId = `comments-${fileId}`;

    // Check if editor already exists
    if (window.fileUploadQuillEditors && window.fileUploadQuillEditors[editorId]) {
        return;
    }

    // Initialize Quill with same toolbar as markdown editor component
    const quill = new Quill(`#${editorId}`, {
        theme: 'snow',
        placeholder: 'Any notes about this file (e.g., date range, special processing)',
        modules: {
            toolbar: [
                ['bold', 'italic'],
                [{ 'header': [1, 2, 3, false] }],
                [{ 'list': 'ordered'}, { 'list': 'bullet' }],
                ['link']
            ]
        }
    });

    // Store editor instance
    if (!window.fileUploadQuillEditors) {
        window.fileUploadQuillEditors = {};
    }
    window.fileUploadQuillEditors[editorId] = quill;

    // Handle focus/blur for styling
    const editorContainer = document.querySelector(`#${editorId}`).closest('.file-upload-markdown-editor');
    quill.on('selection-change', function(range) {
        if (range) {
            editorContainer.classList.add('focused');
        } else {
            editorContainer.classList.remove('focused');
        }
    });

    // Update hidden textarea when content changes
    quill.on('text-change', function() {
        const textarea = document.getElementById(textareaId);
        if (textarea) {
            // Get HTML content for storage
            const html = quill.root.innerHTML;
            // Update both the hidden field and Alpine model
            textarea.value = html === '<p><br></p>' ? '' : html;
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
    });
}
// Check for processing on page load
document.addEventListener('DOMContentLoaded', function() {
    // Check if we should start polling for processing completion
    if (sessionStorage.getItem('naaccord_check_processing') === 'true') {
        sessionStorage.removeItem('naaccord_check_processing');

        // Look for the processing spinner
        const processingSpinner = document.querySelector('.animate-spin');

        if (processingSpinner) {
            const pollInterval = setInterval(async () => {
                try {
                    const response = await fetch(window.location.href, {
                        headers: { 'X-Requested-With': 'XMLHttpRequest' }
                    });

                    if (response.ok) {
                        const html = await response.text();
                        const parser = new DOMParser();
                        const doc = parser.parseFromString(html, 'text/html');

                        // Check if processing is done (spinner gone, patient stats present)
                        const stillProcessing = doc.querySelector('.animate-spin');
                        const hasPatientStats = doc.querySelector('.patient-stats-section') ||
                                              doc.querySelector('[data-processing-complete]');

                        if (!stillProcessing || hasPatientStats) {
                            clearInterval(pollInterval);
                            window.location.reload();
                        }
                    }
                } catch (error) {
                    console.error('Polling error:', error);
                }
            }, 3000); // Poll every 3 seconds
        }
    }
});
