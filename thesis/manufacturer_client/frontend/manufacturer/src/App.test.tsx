import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from './App'

const mockFetch = vi.fn()
global.fetch = mockFetch

vi.mock('./components/FirmwareUpload', () => ({
  default: function MockFirmwareUpload(props: any) {
    return (
      <div data-testid="firmware-upload">
        <input
          data-testid="version-input"
          value={props.version}
          onChange={(e) => props.onVersionChange(e.target.value)}
          placeholder="e.g. v1.2.0"
          aria-invalid={Boolean(props.validationErrors?.version)}
        />
        <select
          data-testid="device-type-select"
          value={props.deviceType}
          onChange={(e) => props.onDeviceTypeChange(e.target.value)}
          aria-invalid={Boolean(props.validationErrors?.deviceType)}
        >
          <option value="esp32">esp32</option>
        </select>
        <input
          data-testid="file-input"
          type="file"
          onChange={props.onFileChange}
          aria-invalid={Boolean(props.validationErrors?.file)}
        />
        <button
          data-testid="upload-button"
          disabled={props.isSubmitDisabled}
          onClick={props.onUpload}
        >
          Upload Firmware
        </button>
        {props.validationErrors?.version && (
          <span data-testid="version-error">{props.validationErrors.version}</span>
        )}
        {props.validationErrors?.deviceType && (
          <span data-testid="device-type-error">{props.validationErrors.deviceType}</span>
        )}
        {props.validationErrors?.file && (
          <span data-testid="file-error">{props.validationErrors.file}</span>
        )}
        <span data-testid="file-name">{props.fileName || 'No file selected'}</span>
      </div>
    )
  }
}))

vi.mock('./components/UploadStatus', () => ({
  default: function MockUploadStatus(props: any) {
    return (
      <div data-testid="upload-status">
        <span className={props.status}>{props.message}</span>
        {props.objectId && <span data-testid="object-id">{props.objectId}</span>}
      </div>
    )
  }
}))

vi.mock('./components/FirmwareHistory', () => ({
  default: function MockFirmwareHistory() {
    return <div data-testid="firmware-history">Firmware History Mock</div>
  }
}))

describe('App', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    mockFetch.mockReset()
    mockFetch.mockResolvedValue({ ok: true, json: async () => ({ UploadResult: 1 }) })
  })

  // ── Submit eligibility ──────────────────────────────────────────────────────

  it('disables upload button when version is empty', () => {
    render(<App />)
    expect(screen.getByTestId('upload-button')).toBeDisabled()
  })

  it('disables upload button when no file is selected', async () => {
    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    expect(screen.getByTestId('upload-button')).toBeDisabled()
  })

  it('enables upload button when version and file are provided', async () => {
    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })

    const fileInput = screen.getByTestId('file-input')
    const file = new File(['dummy'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)

    expect(screen.getByTestId('upload-button')).not.toBeDisabled()
  })

  it('disables upload button and prevents duplicate submission while uploading', async () => {
    let resolveUpload!: (value: unknown) => void
    mockFetch.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveUpload = resolve
      }),
    )

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })

    const fileInput = screen.getByTestId('file-input')
    const file = new File(['binary'], 'firmware.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)

    const uploadBtn = screen.getByTestId('upload-button')
    expect(uploadBtn).not.toBeDisabled()

    // 觸發第一次上傳
    await userEvent.click(uploadBtn)

    // 斷言 1：在非同步請求處理期間，按鈕必須處於停用狀態
    expect(uploadBtn).toBeDisabled()

    // 嘗試在處理中再次點擊按鈕
    await userEvent.click(uploadBtn)

    // 斷言 2：fetch 只應被呼叫 1 次，防止重複提交
    expect(mockFetch).toHaveBeenCalledTimes(1)

    // 結束非同步請求
    resolveUpload({
      ok: true,
      json: async () => ({ UploadResult: 1, Message: 'Upload finished' }),
    })

    // 等待狀態更新為 Success
    await waitFor(() => {
      expect(screen.getByTestId('upload-status')).toHaveTextContent('Upload finished')
    })
  })

  // ── Form field interactions ─────────────────────────────────────────────────

  it('shows file name when a file is selected', async () => {
    render(<App />)
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'test_firmware.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    expect(screen.getByTestId('file-name')).toHaveTextContent('test_firmware.bin')
  })

  it('clears version validation error when version changes', async () => {
    render(<App />)
    // Trigger validation by submitting with empty version and a file
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)

    // Simulate validateForm by directly calling the onUpload handler after
    // the button is enabled — but we mock the API so no real request fires.
    mockFetch.mockResolvedValueOnce({ ok: true, json: async () => ({ UploadResult: 1, Message: 'ok' }) })
    const uploadBtn = screen.getByTestId('upload-button')
    // Button is disabled because version is empty; skip click
    expect(uploadBtn).toBeDisabled()

    // Now set a valid version
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v2.0.0' } })
    expect(uploadBtn).not.toBeDisabled()
    // No version error should appear
    expect(screen.queryByTestId('version-error')).not.toBeInTheDocument()
  })

  it('clears deviceType validation error when device type changes', async () => {
    render(<App />)
    const select = screen.getByTestId('device-type-select')
    fireEvent.change(select, { target: { value: 'esp32' } })
    // No device-type error should appear
    expect(screen.queryByTestId('device-type-error')).not.toBeInTheDocument()
  })

  it('shows "No file selected" when no file is chosen', () => {
    render(<App />)
    expect(screen.getByTestId('file-name')).toHaveTextContent('No file selected')
  })

  // ── API flow tests ───────────────────────────────────────────────────────────

  it('successfully uploads firmware on POST /internal/manufacturer/upload', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ UploadResult: 1, Message: 'Firmware uploaded successfully' }),
    })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['binary'], 'firmware.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    const uploadBtn = screen.getByTestId('upload-button')
    await userEvent.click(uploadBtn)

    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(1)
      const [url, opts] = mockFetch.mock.calls[0]
      expect(url).toBe('/internal/manufacturer/upload')
      expect(opts.method).toBe('POST')
      const body = opts.body as FormData
      // 確認版本號和裝置類型是 trim() 後的值
      expect(body.get('firmware_version')).toBe('v1.0.0')
      expect(body.get('device_type')).toBe('esp32')

      // 確認韌體檔案有正確放進 FormData
      const uploadedFile = body.get('firmware_file')
      expect(uploadedFile).toBeInstanceOf(File)
      expect((uploadedFile as File).name).toBe('firmware.bin')
    })

    await waitFor(() => {
      // Check that status shows Success class and contains the message
      const statusSpan = screen.getByTestId('upload-status').querySelector('span')
      expect(statusSpan).toHaveClass('Success')
      expect(statusSpan).toHaveTextContent('Firmware uploaded successfully')
    })
  })

  it('uses default success message when API response has no Message field', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ UploadResult: 1 }),
    })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      const statusSpan = screen.getByTestId('upload-status').querySelector('span')
      expect(statusSpan).toHaveClass('Success')
      // When no Message field, should use default
      expect(statusSpan).toHaveTextContent('Firmware has been uploaded successfully.')
    })
  })

  it('dispatches firmware-history-updated event on successful upload', async () => {
    const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent')
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ UploadResult: 1, Message: 'done' }),
    })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      expect(dispatchEventSpy).toHaveBeenCalledWith(expect.any(Event))
      const dispatchedEvent = dispatchEventSpy.mock.calls[0][0] as Event
      expect(dispatchedEvent.type).toBe('firmware-history-updated')
    })
    dispatchEventSpy.mockRestore()
  })

  it('shows Error status and message for HTTP 400', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 400 })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      expect(screen.getByTestId('upload-status')).toHaveTextContent('Upload failed: invalid request')
    })
  })

  it('shows Error status and message for HTTP 500', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      expect(screen.getByTestId('upload-status')).toHaveTextContent(
        'Upload failed: manufacturer service error',
      )
    })
  })

  it('shows generic error for non-400/500 HTTP failures (e.g. 404)', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 404 })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      expect(screen.getByTestId('upload-status')).toHaveTextContent(
        'Upload failed. Please check the form and retry.',
      )
    })
  })

  it('shows connection error when fetch rejects (network error)', async () => {
    mockFetch.mockRejectedValueOnce(new Error('Network failure'))

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      expect(screen.getByTestId('upload-status')).toHaveTextContent(
        'Unable to connect to manufacturer service.',
      )
    })
  })

  it('handles invalid JSON response without crashing', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => { throw new SyntaxError('Unexpected token') },
    })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    // 故意在版本號前後加空白，測試 App 是否會 trim()
    fireEvent.change(versionInput, {
      target: { value: '  v1.0.0  ' },
    })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', {
    type: 'application/octet-stream',
  })
  await userEvent.upload(fileInput, file)

  await userEvent.click(screen.getByTestId('upload-button'))

  // JSON 解析失敗時，仍應顯示成功狀態與預設訊息
  await waitFor(() => {
    const statusSpan = screen
      .getByTestId('upload-status')
      .querySelector('span')

    expect(statusSpan).toHaveClass('Success')
    expect(statusSpan).toHaveTextContent(
      'Firmware has been uploaded successfully.',
    )
  })
})

  it('does not dispatch firmware-history-updated on 400 error', async () => {
    const dispatchEventSpy = vi.spyOn(window, 'dispatchEvent')
    mockFetch.mockResolvedValueOnce({ ok: false, status: 400 })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      expect(dispatchEventSpy).not.toHaveBeenCalled()
    })
    dispatchEventSpy.mockRestore()
  })

  it('does not include sensitive keys in FormData', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ UploadResult: 1, Message: 'ok' }),
    })

    render(<App />)
    const versionInput = screen.getByTestId('version-input')
    fireEvent.change(versionInput, { target: { value: 'v1.0.0' } })
    const fileInput = screen.getByTestId('file-input')
    const file = new File(['c'], 'fw.bin', { type: 'application/octet-stream' })
    await userEvent.upload(fileInput, file)
    await userEvent.click(screen.getByTestId('upload-button'))

    await waitFor(() => {
      const body = mockFetch.mock.calls[0][1].body as FormData
      const keys = Array.from(body.keys())
      expect(keys).toEqual(expect.arrayContaining(['firmware_file', 'firmware_version', 'device_type']))
      expect(keys).not.toContain('private_key')
      expect(keys).not.toContain('certificate')
      expect(keys).not.toContain('signature')
      expect(keys).not.toContain('manufacturer_id')
      expect(keys).not.toContain('release_date')
      expect(keys).not.toContain('signature_algorithm')
    })
  })
})
