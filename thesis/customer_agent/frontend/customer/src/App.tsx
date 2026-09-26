import { useCallback, useEffect, useRef, useState } from 'react'
import './App.css'
import Dashboard from './components/Dashboard'
import { getDevicesUrl, getFirmwareUrl } from './api'
import type { CustomerDevice, FirmwareRecord } from './types'

type LoadState = {
  devices: CustomerDevice[]
  firmwares: FirmwareRecord[]
  loading: boolean
  error: string | null
  firmwareRefreshError: string | null
  devicesUnavailable: boolean
}

async function fetchJson(url: string): Promise<unknown> {
  const response = await fetch(url)

  if (!response.ok) {
    throw new Error(`API error: ${response.status}`)
  }

  return response.json()
}

function App() {
  const [state, setState] = useState<LoadState>({
    devices: [],
    firmwares: [],
    loading: true,
    error: null,
    firmwareRefreshError: null,
    devicesUnavailable: false,
  })
  const firmwareRequestInFlight = useRef(false)
  const hasCompletedFirmwareLoad = useRef(false)

  const loadFirmware = useCallback(async () => {
    if (firmwareRequestInFlight.current) {
      return
    }

    firmwareRequestInFlight.current = true
    try {
      const firmwarePayload = await fetchJson(getFirmwareUrl())
      const firmwares =
        (firmwarePayload as { firmwares?: FirmwareRecord[] }).firmwares ?? []

      hasCompletedFirmwareLoad.current = true
      setState((previous) => ({
        ...previous,
        firmwares,
        loading: false,
        firmwareRefreshError: null,
      }))
    } catch (error) {
      setState((previous) => ({
        ...previous,
        loading: false,
        error: previous.loading
          ? (error as Error).message
          : previous.error,
        firmwareRefreshError: previous.loading
          ? null
          : `Firmware refresh failed: ${(error as Error).message}`,
      }))
    } finally {
      firmwareRequestInFlight.current = false
    }
  }, [])

  useEffect(() => {
    let mounted = true

    async function loadDevices() {
      // Devices 端點尚未實作；失敗時以 devicesUnavailable 標記（不偽造成功），
      // 且**不**阻止 firmware 顯示。Devices 不隨 firmware polling / refresh 重新載入。
      try {
        const devicesPayload = await fetchJson(getDevicesUrl())
        const devices =
          (devicesPayload as { devices?: CustomerDevice[] }).devices ?? []

        if (mounted) {
          setState((previous) => ({
            ...previous,
            devices,
            loading: false,
            devicesUnavailable: false,
          }))
        }
      } catch {
        if (mounted) {
          setState((previous) => ({
            ...previous,
            loading: false,
            devicesUnavailable: true,
          }))
        }
      }
    }

    void loadFirmware()
    void loadDevices()

    return () => {
      mounted = false
    }
  }, [loadFirmware])

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      void loadFirmware()
    }, 10_000)

    return () => {
      window.clearInterval(intervalId)
    }
  }, [loadFirmware])

  const handleManualRefresh = useCallback(() => {
    void loadFirmware()
  }, [loadFirmware])

  return (
    <div className="dashboard-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">Customer Portal</p>
          <h1>Customer Firmware Dashboard</h1>
        </div>
      </header>

      <main className="content">
        <Dashboard
          devices={state.devices}
          firmwares={state.firmwares}
          error={state.error}
          firmwareRefreshError={state.firmwareRefreshError}
          onRefreshFirmware={handleManualRefresh}
        />
      </main>
    </div>
  )
}

export default App
