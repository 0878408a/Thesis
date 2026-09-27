import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import FirmwareHistory from '../components/FirmwareHistory'

const mockFetch = vi.fn()
global.fetch = mockFetch

describe('FirmwareHistory', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading state initially', () => {
    mockFetch.mockReturnValueOnce(new Promise(() => {}))
    render(<FirmwareHistory />)
    expect(screen.getByText('Loading firmware history...')).toBeInTheDocument()
  })

  it('fetches and displays history records', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 2,
        next: null,
        previous: null,
        results: [
          {
            object_id: 'obj123',
            metadata_id: 1,
            firmware_version: 'v1.0.0',
            device_type: 'esp32',
            firmware_size: 1024,
            release_date: 3820540800,
            submit_block_result: 'Success',
          },
          {
            object_id: 'obj456',
            metadata_id: 2,
            firmware_version: 'v1.1.0',
            device_type: 'esp32',
            firmware_size: 2048,
            release_date: 3820627200,
            submit_block_result: 'Success',
          },
        ],
      }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText('v1.0.0')).toBeInTheDocument()
      expect(screen.getByText('v1.1.0')).toBeInTheDocument()
      const rows = screen.getAllByRole('row')
      expect(rows.length).toBeGreaterThan(2)
      expect(screen.getByText('1024 bytes')).toBeInTheDocument()
      expect(screen.getByText('2048 bytes')).toBeInTheDocument()
      const uploaded = screen.getAllByText('Uploaded')
      expect(uploaded.length).toBeGreaterThanOrEqual(1)
    })
  })

  it('maps NTP timestamp to Asia/Taipei display time', async () => {
    // NTP timestamp 3820540800 = Unix 1609459200 = 2021-01-25 08:00:00 UTC
    // The component formats this using toLocaleString which may vary by locale,
    // so we check for a reasonable date string rather than a specific one.
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            object_id: '',
            metadata_id: 1,
            firmware_version: 'v1.0.0',
            device_type: 'esp32',
            firmware_size: 1024,
            release_date: 3820540800,
            submit_block_result: 'Success',
          },
        ],
      }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      // NTP timestamp 3820540800
      // = Unix timestamp 1611552000
      // = 2021-01-25 00:00:00 UTC
      // = 2021-01-25 13:20:00 Asia/Taipei
      expect(screen.getByText(/2021-01-25 13:20:00/)).toBeInTheDocument()
    })
  })

  it('shows error when fetch fails', async () => {
    mockFetch.mockResolvedValueOnce({ ok: false, status: 500 })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText('Unable to load firmware history.')).toBeInTheDocument()
    })
  })

  it('renders pagination controls', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ count: 10, next: null, previous: null, results: [] }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText(/Page 1 \/ 1/)).toBeInTheDocument()
    })
  })

  it('shows object ID links in history table', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            object_id: 'iota1test123',
            metadata_id: 1,
            firmware_version: 'v1.0.0',
            device_type: 'esp32',
            firmware_size: 1024,
            release_date: 3820540800,
            submit_block_result: 'Success',
          },
        ],
      }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      const link = screen.getByRole('link', { name: /iota1test123/i })
      expect(link).toBeInTheDocument()
      expect(link).toHaveAttribute(
        'href',
        'https://explorer.iota.org/object/iota1test123?network=testnet',
      )
    })
  })

  it('shows dash when object ID is missing', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({
        count: 1,
        next: null,
        previous: null,
        results: [
          {
            object_id: '',
            metadata_id: 1,
            firmware_version: 'v1.0.0',
            device_type: 'esp32',
            firmware_size: 1024,
            release_date: 3820540800,
            submit_block_result: 'Success',
          },
        ],
      }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText('-')).toBeInTheDocument()
    })
  })

  it('calls fetch with correct page parameter on initial load', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ count: 0, next: null, previous: null, results: [] }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('page=1'))
    })
  })

  // ── Pagination interaction ──────────────────────────────────────────────────

  it('enables Next button when there are multiple pages', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ count: 20, next: null, previous: null, results: [] }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText(/Page 1 \/ 2/)).toBeInTheDocument()
      const nextBtn = screen.getByRole('button', { name: /Next/i })
      expect(nextBtn).not.toBeDisabled()
    })
  })

  it('disables Previous button on first page', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ count: 10, next: null, previous: null, results: [] }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      const prevBtn = screen.getByRole('button', { name: /Previous/i })
      expect(prevBtn).toBeDisabled()
    })
  })

  it('disables Next button on last page', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ count: 10, next: null, previous: null, results: [] }),
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      const nextBtn = screen.getByRole('button', { name: /Next/i })
      expect(nextBtn).toBeDisabled()
    })
  })

  it('navigates to next page when Next is clicked and re-fetches with correct page', async () => {
    mockFetch.mockImplementation(async (url: string) => {
      const pageMatch = (url as string).match(/page=(\d+)/)
      const page = pageMatch ? parseInt(pageMatch[1], 10) : 1
      return {
        ok: true,
        json: async () => ({
          count: 20,
          next: page < 2 ? `/internal/manufacturer/history/?page=${page + 1}` : null,
          previous: page > 1 ? `/internal/manufacturer/history/?page=${page - 1}` : null,
          results: [],
        }),
      }
    })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText(/Page 1 \/ 2/)).toBeInTheDocument()
    })
    const nextBtn = screen.getByRole('button', { name: /Next/i })
    fireEvent.click(nextBtn)
    await waitFor(() => {
      expect(screen.getByText(/Page 2 \/ 2/)).toBeInTheDocument()
      expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('page=2'))
    })
  })

  it('navigates to previous page when Previous is clicked and re-fetches with correct page', async () => {
  mockFetch.mockImplementation(async (url: string) => {
    const pageMatch = (url as string).match(/page=(\d+)/)
    const page = pageMatch ? parseInt(pageMatch[1], 10) : 1

    return {
      ok: true,
      json: async () => ({
        count: 20,
        next: page < 2 ? `/internal/manufacturer/history/?page=${page + 1}` : null,
        previous: page > 1 ? `/internal/manufacturer/history/?page=${page - 1}` : null,
        results: [],
      }),
    }
  })
    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText(/Page 1 \/ 2/)).toBeInTheDocument()
    })
    // Go to page 2 first
    fireEvent.click(screen.getByRole('button', { name: /Next/i }))
    await waitFor(() => {
      expect(screen.getByText(/Page 2 \/ 2/)).toBeInTheDocument()
    })
    // Now go back
    fireEvent.click(screen.getByRole('button', { name: /Previous/i }))
    await waitFor(() => {
      expect(screen.getByText(/Page 1 \/ 2/)).toBeInTheDocument()
      expect(mockFetch).toHaveBeenCalledWith(expect.stringContaining('page=1'))
    })
  })

  // ── History refresh event ────────────────────────────────────────────────────

  it('refetches history when firmware-history-updated event is dispatched', async () => {
    mockFetch
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              object_id: 'obj-new',
              metadata_id: 1,
              firmware_version: 'v2.0.0',
              device_type: 'esp32',
              firmware_size: 2048,
              release_date: 3820540800,
              submit_block_result: 'Success',
            },
          ],
        }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          count: 2,
          next: null,
          previous: null,
          results: [
            {
              object_id: 'obj-new',
              metadata_id: 1,
              firmware_version: 'v2.0.0',
              device_type: 'esp32',
              firmware_size: 2048,
              release_date: 3820540800,
              submit_block_result: 'Success',
            },
            {
              object_id: 'obj-old',
              metadata_id: 2,
              firmware_version: 'v1.0.0',
              device_type: 'esp32',
              firmware_size: 1024,
              release_date: 3820454400,
              submit_block_result: 'Success',
            },
          ],
        }),
      })

    render(<FirmwareHistory />)
    await waitFor(() => {
      expect(screen.getByText('v2.0.0')).toBeInTheDocument()
    })
    // Dispatch the refresh event
    window.dispatchEvent(new Event('firmware-history-updated'))
    await waitFor(() => {
      expect(mockFetch).toHaveBeenCalledTimes(2)
      expect(screen.getByText('v1.0.0')).toBeInTheDocument()
    })
  })
})
