import { useState } from 'react'
import './App.css'
import FirmwareHistory from './components/FirmwareHistory'
import FirmwareUpload from './components/FirmwareUpload'
import UploadStatus from './components/UploadStatus'

type FirmwareStatus = 'Ready' | 'Uploading' | 'Success' | 'Error'
type ValidationErrors = Partial<Record<'version' | 'deviceType' | 'file', string>>

type SelectedFirmwareFile = {
  file: File
  name: string
  size: number
  sizeLabel: string
}

const formatFileSize = (size: number) => {
  if (size < 1024) return `${size} B`

  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`
  }

  return `${(size / (1024 * 1024)).toFixed(1)} MB`
}

function App() {
  const [version, setVersion] = useState('')
  const [deviceType, setDeviceType] = useState('esp32')
  const [selectedFile, setSelectedFile] =
    useState<SelectedFirmwareFile | null>(null)

  const [status, setStatus] =
    useState<FirmwareStatus>('Ready')

  const [statusMessage, setStatusMessage] =
    useState('Ready for firmware upload.')

  const [validationErrors, setValidationErrors] =
    useState<ValidationErrors>({})

  const isSubmitDisabled =
    !version.trim() || !selectedFile || status === 'Uploading'

  const validateForm = () => {
    const errors: ValidationErrors = {}

    if (!version.trim()) {
      errors.version = 'Firmware Version is required.'
    }

    if (!deviceType.trim()) {
      errors.deviceType = 'Device Type is required.'
    }

    if (!selectedFile) {
      errors.file = 'Please select a firmware file.'
    }

    setValidationErrors(errors)

    return Object.keys(errors).length === 0
  }

  const handleFileChange = (
    event: React.ChangeEvent<HTMLInputElement>,
  ) => {
    const file = event.target.files?.[0]

    if (!file) {
      setSelectedFile(null)

      setValidationErrors((previous) => ({
        ...previous,
        file: 'Please select a firmware file.',
      }))

      return
    }

    setSelectedFile({
      file,
      name: file.name,
      size: file.size,
      sizeLabel: formatFileSize(file.size),
    })

    setValidationErrors((previous) => ({
      ...previous,
      file: undefined,
    }))
  }

  const handleUpload = async () => {
    if (status === 'Uploading') {
      return
    }

    const formIsValid = validateForm()

    if (!formIsValid || !selectedFile?.file) {
      setStatus('Error')
      setStatusMessage(
        'Upload failed. Please check the form and retry.',
      )
      return
    }

    setStatus('Uploading')
    setStatusMessage(
      'Firmware is being validated and uploaded.',
    )

    const formData = new FormData()

    formData.append(
      'firmware_file',
      selectedFile.file,
      selectedFile.file.name,
    )

    formData.append(
      'firmware_version',
      version.trim(),
    )

    formData.append(
      'device_type',
      deviceType.trim(),
    )

    try {
      const response = await fetch(
        '/internal/manufacturer/upload',
        {
          method: 'POST',
          body: formData,
        },
      )

      let payload: Record<string, unknown> = {}

      try {
        payload =
          (await response.json()) as Record<string, unknown>
      } catch {
        payload = {}
      }

      const uploadResult = payload.UploadResult

      if (
        response.ok &&
        (uploadResult === undefined || uploadResult === 1)
      ) {
        setStatus('Success')

        setStatusMessage(
          typeof payload.Message === 'string' &&
            payload.Message.trim()
            ? payload.Message
            : 'Firmware has been uploaded successfully.',
        )

        /*
        * 通知 FirmwareHistory：
        * 韌體已經成功上傳，重新取得最新歷史紀錄。
        */
        window.dispatchEvent(
          new Event('firmware-history-updated'),
        )

        /*
        * Upload API does not return object_id.
        *
        * FirmwareHistory obtains the real firmware history
        * and object_id from the backend History API.
        */

        return
      }

      setStatus('Error')

      if (response.status === 400) {
        setStatusMessage(
          'Upload failed: invalid request',
        )
      } else if (response.status === 500) {
        setStatusMessage(
          'Upload failed: manufacturer service error',
        )
      } else {
        setStatusMessage(
          'Upload failed. Please check the form and retry.',
        )
      }
    } catch (error) {
      console.error(
        'Manufacturer service request failed:',
        error,
      )

      setStatus('Error')
      setStatusMessage(
        'Unable to connect to manufacturer service.',
      )
    }
  }

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Manufacturer Portal</p>
          <h1>Firmware Dashboard</h1>
        </div>
      </header>

      <main className="content">
        <FirmwareUpload
          version={version}
          deviceType={deviceType}
          fileName={
            selectedFile?.name ?? 'No file selected'
          }
          fileSize={
            selectedFile?.sizeLabel ?? ''
          }
          isSubmitDisabled={isSubmitDisabled}
          validationErrors={validationErrors}
          onVersionChange={(newValue) => {
            setVersion(newValue)

            setValidationErrors((previous) => ({
              ...previous,
              version: undefined,
            }))
          }}
          onDeviceTypeChange={(newValue) => {
            setDeviceType(newValue)

            setValidationErrors((previous) => ({
              ...previous,
              deviceType: undefined,
            }))
          }}
          onFileChange={handleFileChange}
          onUpload={handleUpload}
        />

        <UploadStatus
          status={status}
          message={statusMessage}
        />

        <FirmwareHistory />
      </main>
    </div>
  )
}

export default App

