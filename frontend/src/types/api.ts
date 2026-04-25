export type BucketType = 'answer' | 'fact_check' | 'talking_point' | 'question'
export type SignalState = 'weak' | 'normal' | 'urgent'

export type TranscriptTurn = {
  id: string
  text: string
  start_ms: number
  end_ms: number
  confidence?: number | null
}

export type SuggestionCard = {
  bucket: BucketType
  text: string
  confidence: number
  evidence: string[]
  verdict?: string | null
  supporting_points?: string[]
  uncertainties?: string[]
}

export type RefreshSuggestionsRequest = {
  session_id: string
  recent_user_turns: TranscriptTurn[]
  force_refresh?: boolean
  source_policy?: {
    enable_conditional_web: boolean
    approved_sources: string[]
    approved_fact_sources: Array<{
      source_id?: string
      type?: string
      title?: string
      content: string
      uri?: string
    }>
  }
}

export type RefreshSuggestionsResponse = {
  session_id: string
  batch_key: string
  cards: SuggestionCard[]
  omitted_bucket: BucketType
  signal_state: SignalState
  scores: Record<BucketType, number>
  timings: {
    total_ms: number
    state_ms: number
    llm_main_ms: number
    retrieval_ms: number
    verify_ms: number
    finalize_ms: number
  }
  metadata?: Record<string, string | number | boolean>
}

export type ExpandSuggestionResponse = {
  bucket: BucketType
  expanded_text: string
  supporting_points: string[]
  uncertainties: string[]
  evidence_used: string[]
}

export type ChatMessageResponse = {
  session_id: string
  answer: string
  supporting_points: string[]
  uncertainties: string[]
  evidence_used: string[]
}

export type TranscriptionResponse = {
  session_id: string
  speaker: 'user'
  turns: TranscriptTurn[]
  provider: string
  model: string
  fallback_used: boolean
  error?: string | null
}
