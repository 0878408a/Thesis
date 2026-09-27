type FirmwareUploadProps = {
  version: string
  deviceType: string
  fileName: string
  fileSize: string
  isSubmitDisabled: boolean
  validationErrors: Record<string, string>
  onVersionChange: (value: string) => void
  onDeviceTypeChange: (value: string) => void
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void
  onUpload: () => void
}

function FirmwareUpload({
  version,
  deviceType,
  fileName,
  fileSize,
  isSubmitDisabled,
  validationErrors,
  onVersionChange,
  onDeviceTypeChange,
  onFileChange,
  onUpload,
}: FirmwareUploadProps) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Firmware Upload</h2>
      </div>

      <div className="form-grid">
        <label className="field">
          <span>Firmware Version</span>
          <input
            type="text"
            value={version}
            onChange={(event) => onVersionChange(event.target.value)}
            placeholder="e.g. v1.2.0"
            aria-invalid={Boolean(validationErrors.version)}
          />
          {validationErrors.version && (
            <small className="error-text">{validationErrors.version}</small>
          )}
        </label>

        <label className="field">
          <span>Device Type</span>
          <select
            value={deviceType}
            onChange={(event) => onDeviceTypeChange(event.target.value)}
            aria-invalid={Boolean(validationErrors.deviceType)}
          >
            <option value="esp32">esp32</option>
          </select>
          {validationErrors.deviceType && (
            <small className="error-text">{validationErrors.deviceType}</small>
          )}
        </label>
      </div>

      <div className="upload-box">
        <label className="file-picker">
          <span>Firmware File</span>
          <input type="file" onChange={onFileChange} aria-invalid={Boolean(validationErrors.file)} />
        </label>

        <div className="file-summary">
          <strong>Selected file:</strong> {fileName || 'No file selected'}
          {fileSize ? ` (${fileSize})` : ''}
        </div>

        {validationErrors.file && (
          <small className="error-text">{validationErrors.file}</small>
        )}
      </div>

      <button
        type="button"
        className="primary-button"
        onClick={onUpload}
        disabled={isSubmitDisabled}
      >
        Upload Firmware
      </button>
    </section>
  )
}

export default FirmwareUpload
