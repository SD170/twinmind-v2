import type { BucketType, SignalState, SuggestionCard, TranscriptTurn } from '../../types/api'

/** Stable bucket order for sorting suggestion cards in exports. */
const BUCKET_ORDER: BucketType[] = ['answer', 'fact_check', 'talking_point', 'question']

function bucketRank(bucket: BucketType): number {
  const i = BUCKET_ORDER.indexOf(bucket)
  return i === -1 ? 99 : i
}

export type StoredSuggestionBatch = {
  id: string
  createdAt: number
  omittedBucket: string
  latencyMs: number
  signalState?: SignalState
  scores?: Record<BucketType, number>
  cards: SuggestionCard[]
}

export function buildTrajectoryJson(params: {
  sessionId: string
  transcriptTurns: TranscriptTurn[]
  suggestionBatches: StoredSuggestionBatch[]
}): Record<string, unknown> {
  const transcript = [...params.transcriptTurns]
    .sort((a, b) => a.start_ms - b.start_ms)
    .map((t) => ({
      id: t.id,
      text: t.text,
      start_ms: t.start_ms,
      end_ms: t.end_ms,
      confidence: t.confidence ?? null,
    }))

  const suggestionBatches = [...params.suggestionBatches]
    .sort((a, b) => a.createdAt - b.createdAt)
    .map((batch, order) => {
      const suggestions = [...batch.cards]
        .sort((a, b) => bucketRank(a.bucket) - bucketRank(b.bucket))
        .map((c) => ({
          bucket: c.bucket,
          text: c.text,
          confidence: c.confidence,
          evidence: c.evidence,
          verdict: c.verdict ?? null,
        }))

      const out: Record<string, unknown> = {
        order,
        batch_id: batch.id,
        created_at: batch.createdAt,
        omitted_bucket: batch.omittedBucket,
        latency_ms: batch.latencyMs,
        suggestions,
      }
      if (batch.signalState !== undefined) {
        out.signal_state = batch.signalState
      }
      if (batch.scores !== undefined) {
        out.scores = batch.scores
      }
      return out
    })

  return {
    session_id: params.sessionId,
    exported_at: new Date().toISOString(),
    transcript,
    suggestion_batches: suggestionBatches,
  }
}

export function formatTrajectoryJson(data: Record<string, unknown>): string {
  return `${JSON.stringify(data, null, 2)}\n`
}
