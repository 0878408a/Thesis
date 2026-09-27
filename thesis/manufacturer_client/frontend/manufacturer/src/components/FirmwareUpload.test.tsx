import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import FirmwareUpload from '../components/FirmwareUpload'

describe('FirmwareUpload', () => {
  const defaultProps = {
    version: '',
    deviceType: 'esp32',
    fileName: '',
    fileSize: '',
    isSubmitDisabled: true,
    validationErrors: {},
    onVersionChange: vi.fn(),
    onDeviceTypeChange: vi.fn(),
    onFileChange: vi.fn(),
    onUpload: vi.fn(),
  }

  it('displays version input with current value', () => {
    render(<FirmwareUpload {...defaultProps} version="v1.2.0" />)
    const input = screen.getByLabelText(/firmware version/i)
    expect(input).toBeInTheDocument()
    expect(input).toHaveValue('v1.2.0')
  })

  it('displays device type select with esp32 option', () => {
    render(<FirmwareUpload {...defaultProps} />)
    const select = screen.getByLabelText(/device type/i)
    expect(select).toBeInTheDocument()
    expect(select).toHaveValue('esp32')
  })

  it('shows "No file selected" when no file is chosen', () => {
    render(<FirmwareUpload {...defaultProps} />)
    expect(screen.getByText(/no file selected/i)).toBeInTheDocument()
  })

  it('shows selected file name and size', () => {
    render(<FirmwareUpload {...defaultProps} fileName="firmware.bin" fileSize="2.5 MB" />)
    expect(screen.getByText(/firmware\.bin/)).toBeInTheDocument()
    expect(screen.getByText(/2\.5 MB/)).toBeInTheDocument()
  })

  it('calls onVersionChange when version input changes', () => {
    render(<FirmwareUpload {...defaultProps} />)
    const input = screen.getByLabelText(/firmware version/i)
    fireEvent.change(input, { target: { value: 'v2.0.0' } })
    expect(defaultProps.onVersionChange).toHaveBeenCalledWith('v2.0.0')
  })

  it('calls onDeviceTypeChange when device type changes', () => {
    render(<FirmwareUpload {...defaultProps} />)
    const select = screen.getByLabelText(/device type/i)
    fireEvent.change(select, { target: { value: 'esp32' } })
    expect(defaultProps.onDeviceTypeChange).toHaveBeenCalledWith('esp32')
  })

  it('calls onFileChange when file input changes', () => {
    render(<FirmwareUpload {...defaultProps} />)
    const input = screen.getByLabelText(/firmware file/i)
    const changeEvent = { target: { files: [new File(['test'], 'test.bin')] } }
    fireEvent.change(input, changeEvent)
    expect(defaultProps.onFileChange).toHaveBeenCalled()
  })

  it('calls onUpload when upload button is clicked', () => {
    render(<FirmwareUpload {...defaultProps} isSubmitDisabled={false} />)
    const button = screen.getByRole('button', { name: /upload firmware/i })
    fireEvent.click(button)
    expect(defaultProps.onUpload).toHaveBeenCalled()
  })

  it('disables upload button when isSubmitDisabled is true', () => {
    render(<FirmwareUpload {...defaultProps} isSubmitDisabled={true} />)
    const button = screen.getByRole('button', { name: /upload firmware/i })
    expect(button).toBeDisabled()
  })

  it('enables upload button when isSubmitDisabled is false', () => {
    render(<FirmwareUpload {...defaultProps} isSubmitDisabled={false} />)
    const button = screen.getByRole('button', { name: /upload firmware/i })
    expect(button).not.toBeDisabled()
  })

  it('shows validation error for version when present', () => {
    render(<FirmwareUpload {...defaultProps} validationErrors={{ version: 'Version is required' }} />)
    expect(screen.getByText('Version is required')).toBeInTheDocument()
  })

  it('shows validation error for deviceType when present', () => {
    render(<FirmwareUpload {...defaultProps} validationErrors={{ deviceType: 'Device type is required' }} />)
    expect(screen.getByText('Device type is required')).toBeInTheDocument()
  })

  it('shows validation error for file when present', () => {
    render(<FirmwareUpload {...defaultProps} validationErrors={{ file: 'Please select a file' }} />)
    expect(screen.getByText('Please select a file')).toBeInTheDocument()
  })

  it('has aria-invalid attribute on inputs when validation errors exist', () => {
    render(
      <FirmwareUpload
        {...defaultProps}
        validationErrors={{ version: 'Required', deviceType: 'Required', file: 'Required' }}
      />
    )
    const versionInput = screen.getByLabelText(/firmware version/i)
    const deviceSelect = screen.getByLabelText(/device type/i)
    const fileInput = screen.getByLabelText(/firmware file/i)
    
    expect(versionInput).toHaveAttribute('aria-invalid', 'true')
    expect(deviceSelect).toHaveAttribute('aria-invalid', 'true')
    expect(fileInput).toHaveAttribute('aria-invalid', 'true')
  })
})
