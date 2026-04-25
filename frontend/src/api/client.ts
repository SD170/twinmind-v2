import type {
  ChatMessageResponse,
  ExpandSuggestionResponse,
  RefreshSuggestionsRequest,
  RefreshSuggestionsResponse,
  SuggestionCard,
  TranscriptionResponse,
} from '../types/api'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000'

async function parseResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`
    try {
      const payload = (await response.json()) as { detail?: string }
      if (payload.detail) {
        detail = payload.detail
      }
    } catch {
      // Ignore parse errors for non-JSON responses.
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function getHealth() {
  const response = await fetch(`${API_BASE_URL}/health`)
  return parseResponse<{ status: string }>(response)
}

export async function transcribeAudio(params: {
  sessionId: string
  startMs: number
  endMs: number
  audioBlob: Blob
}): Promise<TranscriptionResponse> {
  const form = new FormData()
  form.append('session_id', params.sessionId)
  form.append('start_ms', String(params.startMs))
  form.append('end_ms', String(params.endMs))
  form.append('audio_file', params.audioBlob, 'chunk.webm')

  const response = await fetch(`${API_BASE_URL}/api/v1/transcription`, {
    method: 'POST',
    body: form,
  })
  return parseResponse<TranscriptionResponse>(response)
}

export async function refreshSuggestions(
  request: RefreshSuggestionsRequest
): Promise<RefreshSuggestionsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/suggestions/refresh`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  })
  return parseResponse<RefreshSuggestionsResponse>(response)
}

export async function expandSuggestion(params: {
  sessionId: string
  clickedCard: SuggestionCard
  prompt?: string
}): Promise<ExpandSuggestionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/suggestions/expand`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: params.sessionId,
      clicked_card: params.clickedCard,
      prompt: params.prompt ?? '',
    }),
  })
  return parseResponse<ExpandSuggestionResponse>(response)
}

export async function sendChatMessage(params: {
  sessionId: string
  message: string
}): Promise<ChatMessageResponse> {
  const response = await fetch(`${API_BASE_URL}/api/v1/chat/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: params.sessionId,
      message: params.message,
    }),
  })
  return parseResponse<ChatMessageResponse>(response)
}
