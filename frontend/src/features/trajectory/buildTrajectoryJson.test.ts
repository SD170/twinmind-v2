import { describe, expect, it } from 'vitest'

import { buildTrajectoryJson, formatTrajectoryJson, type StoredSuggestionBatch } from './buildTrajectoryJson'
import type { TranscriptTurn } from '../../types/api'

describe('buildTrajectoryJson', () => {
  it('sorts transcript by time, batches by createdAt, and cards by bucket', () => {
    const t1: TranscriptTurn = {
      id: 'a',
      text: 'second',
      start_ms: 5000,
      end_ms: 6000,
      confidence: null,
    }
    const t2: TranscriptTurn = {
      id: 'b',
      text: 'first',
      start_ms: 0,
      end_ms: 2000,
      confidence: null,
    }

    const b1: StoredSuggestionBatch = {
      id: 'late',
      createdAt: 2000,
      omittedBucket: 'fact_check',
      latencyMs: 100,
      cards: [
        { bucket: 'question', text: 'q', confidence: 0.4, evidence: [] },
        { bucket: 'answer', text: 'a', confidence: 0.9, evidence: [] },
      ],
    }
    const b0: StoredSuggestionBatch = {
      id: 'early',
      createdAt: 1000,
      omittedBucket: 'question',
      latencyMs: 90,
      cards: [{ bucket: 'talking_point', text: 't', confidence: 0.5, evidence: [] }],
    }

    const out = buildTrajectoryJson({
      sessionId: 's1',
      transcriptTurns: [t1, t2],
      suggestionBatches: [b1, b0],
    })

    expect((out.transcript as object[]).map((x) => (x as { id: string }).id)).toEqual(['b', 'a'])
    const batches = out.suggestion_batches as object[]
    expect(batches[0]).toMatchObject({ batch_id: 'early' })
    expect(batches[1]).toMatchObject({ batch_id: 'late' })
    const s1 = (batches[1] as { suggestions: { bucket: string }[] }).suggestions
    expect(s1.map((c) => c.bucket)).toEqual(['answer', 'question'])
  })

  it('formats with trailing newline', () => {
    const s = formatTrajectoryJson({ a: 1 })
    expect(s.endsWith('\n')).toBe(true)
  })
})
