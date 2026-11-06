"""One byte-based upload policy for application validation and Django settings."""
MIB = 1024 * 1024
DOCUMENT_MAX_BYTES = 20 * MIB
IMAGE_MAX_BYTES = 10 * MIB
# Also accommodates 20 MiB PDFs or two 10 MiB images in legacy Base64 JSON.
UPLOAD_REQUEST_MAX_BYTES = 32 * MIB
IMAGE_REQUEST_MAX_BYTES = UPLOAD_REQUEST_MAX_BYTES
FILE_MEMORY_MAX_BYTES = MIB
