import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { getCapabilities, getHealth } from '@/lib/api'

vi.mock('@/lib/api', () => ({ getHealth: vi.fn(), getCapabilities: vi.fn() }))

function renderApp(route = '/workspace/captioning') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}><MemoryRouter initialEntries={[route]}><App /></MemoryRouter></QueryClientProvider>)
}

describe('VisionLab shell', () => {
  beforeEach(() => {
    vi.mocked(getHealth).mockResolvedValue({ status: 'ok', service: 'visionlab-api', version: '0.1.0', environment: 'test' })
    vi.mocked(getCapabilities).mockResolvedValue([
      { id: 'captioning', name: 'Image Captioning', status: 'planned', phase: 4 },
      { id: 'vqa', name: 'Visual Question Answering', status: 'planned', phase: 5 },
      { id: 'analysis', name: 'Image Analysis', status: 'planned', phase: 4 },
      { id: 'objects', name: 'Object and Region Understanding', status: 'planned', phase: 3 },
      { id: 'accessibility', name: 'Accessible Image Descriptions', status: 'planned', phase: 5 },
    ])
  })

  it('connects to the API and marks future inference as planned', async () => {
    renderApp()
    expect(await screen.findByText('API connected')).toBeInTheDocument()
    expect(await screen.findByText('Phase 4')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /upload media/i })).toBeDisabled()
    expect(screen.getByText('No analysis yet')).toBeInTheDocument()
  })

  it('navigates between modules and switches theme', async () => {
    renderApp()
    fireEvent.click(screen.getByRole('link', { name: /visual q&a/i }))
    expect(screen.getByRole('heading', { name: 'Visual Question Answering' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Switch to light theme' }))
    expect(document.documentElement).toHaveAttribute('data-theme', 'light')
  })

  it('shows disconnected state when the backend is unavailable', async () => {
    vi.mocked(getHealth).mockRejectedValue(new Error('offline'))
    renderApp()
    expect(await screen.findByText('API disconnected')).toBeInTheDocument()
    expect(screen.getByText('Backend unavailable')).toBeInTheDocument()
  })
})

