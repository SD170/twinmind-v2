import { describe, expect, it } from 'vitest'

import { buildRefreshRequest } from './buildRefreshRequest'

function makeTurn(index: number) {
  return {
    id: `t-${index}`,
    text: `turn ${index}`,
    start_ms: index * 1000,
    end_ms: index * 1000 + 500,
    confidence: null,
  }
}

describe('buildRefreshRequest', () => {
  it('caps transcript windows to last 30 turns', () => {
    const userTurns = Array.from({ length: 35 }, (_, index) => makeTurn(index))

    const out = buildRefreshRequest({
      sessionId: 'session-1',
      userTurns,
      forceRefresh: true,
    })

    expect(out.recent_user_turns).toHaveLength(30)
    expect(out.recent_user_turns[0].id).toBe('t-5')
    expect(out.force_refresh).toBe(true)
  })
})
