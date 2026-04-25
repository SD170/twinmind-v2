import type { RefreshSuggestionsRequest, TranscriptTurn } from '../../types/api'

export function buildRefreshRequest(params: {
  sessionId: string
  userTurns: TranscriptTurn[]
  forceRefresh?: boolean
}): RefreshSuggestionsRequest {
  return {
    session_id: params.sessionId,
    recent_user_turns: params.userTurns.slice(-30),
    force_refresh: params.forceRefresh ?? false,
    source_policy: {
      enable_conditional_web: true,
      approved_sources: [],
      approved_fact_sources: [],
    },
  }
}
