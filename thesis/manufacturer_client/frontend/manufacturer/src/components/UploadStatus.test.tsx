import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import UploadStatus from '../components/UploadStatus'

describe('UploadStatus', () => {
  const defaultProps = {
    status: 'Ready' as const,
    message: 'Ready for firmware upload.',
  }

  it('displays the status badge and message', () => {
    render(<UploadStatus {...defaultProps} />)
    expect(screen.getByText('Ready')).toBeInTheDocument()
    expect(screen.getByText('Ready for firmware upload.')).toBeInTheDocument()
  })

  it.each`
    status         | className
    ${'Ready'}     | ${'.status-badge.ready'}
    ${'Uploading'} | ${'.status-badge.uploading'}
    ${'Success'}   | ${'.status-badge.success'}
    ${'Error'}     | ${'.status-badge.error'}
  `('applies correct status class for $status', ({ status, className }) => {
    const { container } = render(<UploadStatus {...defaultProps} status={status} />)
    const badge = container.querySelector(className)
    expect(badge).toBeInTheDocument()
  })

  it('shows object ID link with correct attributes', () => {
    render(<UploadStatus {...defaultProps} objectId="iota1abc123" />)
    const link = screen.getByRole('link', { name: /iota1abc123/i })
    expect(link).toBeInTheDocument()
    expect(link).toHaveAttribute(
      'href',
      'https://explorer.iota.org/object/iota1abc123?network=testnet',
    )
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('does not show object ID link when objectId is falsy', () => {
    ;[undefined, ''].forEach((value) => {
      const { container } = render(<UploadStatus {...defaultProps} objectId={value} />)
      expect(container.querySelector('a')).not.toBeInTheDocument()
    })
  })
})
