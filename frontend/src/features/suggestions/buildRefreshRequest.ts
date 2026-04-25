import type { RefreshSuggestionsRequest, TranscriptTurn } from '../../types/api'

export function buildRefreshRequest(params: {
  sessionId: string
  userTurns: TranscriptTurn[]
  forceRefresh?: boolean
  contextWindowTurns?: number
  enableConditionalWeb?: boolean
  approvedSources?: string[]
}): RefreshSuggestionsRequest {
  const windowTurns = Math.max(1, params.contextWindowTurns ?? 30)
  return {
    session_id: params.sessionId,
    recent_user_turns: params.userTurns.slice(-windowTurns),
    force_refresh: params.forceRefresh ?? false,
    source_policy: {
      enable_conditional_web: params.enableConditionalWeb ?? true,
      approved_sources: params.approvedSources ?? [],
      approved_fact_sources: [],
    },
  }
}
