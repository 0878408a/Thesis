type UploadStatusProps = {
  status: 'Ready' | 'Uploading' | 'Success' | 'Error'
  message: string
  objectId?: string | undefined
}

function UploadStatus({ status, message, objectId }: UploadStatusProps) {
  const statusClass = `status-badge ${status.toLowerCase()}`

  return (
    <section className="panel">
      <div className="panel-header">
        <h2>Upload Status</h2>
      </div>

      <div className="status-row">
        <span className={statusClass}>{status}</span>
        <p>{message}</p>
      </div>

      {objectId && (
        <div className="panel-footer">
          <strong>Object ID:</strong>{' '}
          <a href={`https://explorer.iota.org/object/${objectId}?network=testnet`} target="_blank" rel="noopener noreferrer">
            {objectId}
          </a>
        </div>
      )}
    </section>
  )
}

export default UploadStatus
