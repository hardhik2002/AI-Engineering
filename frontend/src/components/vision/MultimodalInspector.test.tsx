import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { VQAInspector } from './VQAInspector'
import { AccessibilityInspector } from './AccessibilityInspector'
import { askImage, generateDescription, getVisionProviders, listConversations, listDescriptions } from '@/lib/multimodal'
import { listCaptions } from '@/lib/caption'

vi.mock('@/lib/multimodal', () => ({
  askImage: vi.fn(), deleteConversation: vi.fn(), getVisionProviders: vi.fn(),
  listConversations: vi.fn(), listDescriptions: vi.fn(), generateDescription: vi.fn(),
  saveDescription: vi.fn(),
}))
vi.mock('@/lib/caption', () => ({ listCaptions: vi.fn() }))

const mediaId = 'f2af6ea3-92c0-4eba-9afd-d6a9a225e3a9'
function renderInspector(view: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  return render(<QueryClientProvider client={client}>{view}</QueryClientProvider>)
}

describe('multimodal inspectors', () => {
  beforeEach(() => {
    vi.clearAllMocks(); localStorage.clear()
    vi.mocked(getVisionProviders).mockResolvedValue({
      vqa: { provider: 'openai', state: 'configured', model: 'test' },
      accessibility: { provider: 'openai', state: 'unconfigured', model: 'test' },
    })
    vi.mocked(listConversations).mockResolvedValue([])
    vi.mocked(listDescriptions).mockResolvedValue([])
    vi.mocked(listCaptions).mockResolvedValue([])
  })

  it('requires consent before sending a question and displays the saved answer', async () => {
    vi.mocked(askImage).mockResolvedValue({
      conversation_id: 'conversation', media_id: mediaId, created_at: '2026-10-30T00:00:00Z',
      updated_at: '2026-10-30T00:00:01Z', messages: [
        { message_id: 'u', role: 'user', text: 'What color?', created_at: '2026-10-30T00:00:00Z', grounding_status: null, uncertainty_note: null, provider: null, model: null, duration_ms: null, usage: null },
        { message_id: 'a', role: 'assistant', text: 'Red.', created_at: '2026-10-30T00:00:01Z', grounding_status: 'supported', uncertainty_note: null, provider: 'openai', model: 'test', duration_ms: 12, usage: { input_tokens: 8, output_tokens: 2, total_tokens: 10 } },
      ],
    })
    renderInspector(<VQAInspector mediaId={mediaId} isVideo={false} />)
    fireEvent.change(screen.getByLabelText('Question about image'), { target: { value: 'What color?' } })
    expect(screen.getByRole('button', { name: 'Ask image' })).toBeDisabled()
    expect(askImage).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Ask image' }))
    await waitFor(() => expect(askImage).toHaveBeenCalledWith(mediaId, 'What color?', null, true))
    expect(await screen.findByText('Red.')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'New conversation' }))
    fireEvent.change(screen.getByLabelText('Question about image'), { target: { value: 'What shape?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Ask image' }))
    await waitFor(() => expect(askImage).toHaveBeenLastCalledWith(mediaId, 'What shape?', null, true))
  })

  it('creates decorative empty alt text locally without consent', async () => {
    vi.mocked(generateDescription).mockResolvedValue({
      result_id: 'result', media_id: mediaId, purpose: 'decorative', context: '', audience: '',
      function: '', source: 'decorative_local', generated: { alt_text: '', detailed_description: null,
        extended_description: null }, edited: null, model: null, provider: null,
      duration_ms: null, usage: null, version: 1,
      created_at: '2026-10-30T00:00:00Z', updated_at: '2026-10-30T00:00:00Z',
    })
    renderInspector(<AccessibilityInspector mediaId={mediaId} isVideo={false} />)
    fireEvent.change(screen.getByLabelText('Image purpose'), { target: { value: 'decorative' } })
    fireEvent.click(screen.getByRole('button', { name: 'Create empty alt text' }))
    await waitFor(() => expect(generateDescription).toHaveBeenCalledWith(mediaId,
      expect.objectContaining({ purpose: 'decorative', consent_external_transfer: false })))
    expect(await screen.findByLabelText('Alt text')).toHaveValue('')
    expect(screen.getByText(/Source: decorative local/)).toBeInTheDocument()
  })
})
