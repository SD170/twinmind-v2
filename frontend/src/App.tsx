import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  expandSuggestion,
  getHealth,
  refreshSuggestions,
  sendChatMessage,
  transcribeAudio,
} from './api/client'
import { buildRefreshRequest } from './features/suggestions/buildRefreshRequest'
import {
  bucketUi,
  cardHeadline,
  formatTranscriptTime,
  labelForBucketKey,
  relTime,
} from './features/dashboard/stitchUtils'
import {
  buildTrajectoryJson,
  formatTrajectoryJson,
  type StoredSuggestionBatch,
} from './features/trajectory/buildTrajectoryJson'
import type { SignalState, SuggestionCard, TranscriptTurn } from './types/api'

const TRANSCRIPTION_SEGMENT_MS = 30_000
const SUGGESTION_REFRESH_SECONDS = 30

type ChatRole = 'user' | 'assistant'
type ChatEntry = {
  id: string
  role: ChatRole
  text: string
  at: number
  supportingPoints?: string[]
  uncertainties?: string[]
  evidenceUsed?: string[]
}

function pickAudioMimeType(): string {
  const candidates = ['audio/webm;codecs=opus', 'audio/webm']
  for (const type of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(type)) {
      return type
    }
  }
  return ''
}

function makeId() {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `id-${Date.now()}-${Math.floor(Math.random() * 10000)}`
}

function signalPillClass(state: SignalState | undefined): string {
  if (state === 'urgent') return 'text-red-300 border-red-500/40 bg-red-500/10'
  if (state === 'weak') return 'text-white/40 border-white/10 bg-white/5'
  return 'text-primary border-primary/30 bg-primary/10'
}

function verdictPill(verdict: string): string {
  if (verdict === 'supported') return 'text-emerald-400'
  if (verdict === 'refuted') return 'text-rose-400'
  return 'text-amber-200'
}

type SuggestionGridProps = {
  cards: SuggestionCard[]
  batchId: string
  opacity: number
  expandingKey: string | null
  onExpand: (batchId: string, card: SuggestionCard, index: number) => void
}

function SuggestionGrid({
  cards,
  batchId,
  opacity,
  expandingKey,
  onExpand,
}: SuggestionGridProps) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-sm transition-opacity"
      style={{ opacity }}
    >
      {cards.map((card, index) => {
        const ui = bucketUi(card.bucket)
        const { title, body } = cardHeadline(card.text)
        const expandKey = `${batchId}-${index}`
        return (
          <div
            key={expandKey}
            className={`glass-card p-sm rounded-xl ${ui.borderClass} group flex flex-col ${
              card.evidence.length || (card.supporting_points?.length ?? 0) > 0 ? 'min-h-[8rem]' : ''
            }`}
          >
            <div className="flex justify-between items-start mb-2">
              <div className="flex flex-col gap-1 max-w-[78%]">
                <div className="flex flex-wrap gap-1">
                  <span
                    className={`${ui.tagClass} text-[10px] font-bold px-2 py-0.5 rounded-full uppercase leading-tight`}
                  >
                    {ui.label}
                  </span>
                  {card.confidence > 0 && (
                    <span className="text-[10px] text-white/30 self-center">
                      {Math.round(card.confidence * 100)}% conf
                    </span>
                  )}
                </div>
                {card.verdict && (
                  <span className={`text-[10px] font-semibold ${verdictPill(card.verdict)}`}>
                    {card.verdict}
                  </span>
                )}
              </div>
              <span
                className={`material-symbols-outlined text-white/20 text-sm group-hover:text-primary transition-colors ${
                  card.bucket === 'fact_check' ? 'group-hover:text-orange-400' : ''
                }`}
                aria-hidden
              >
                {ui.icon}
              </span>
            </div>
            <h4 className="text-sm font-bold text-white mb-1 leading-snug line-clamp-2">{title}</h4>
            {body && <p className="text-xs text-on-surface/60 line-clamp-2 flex-1">{body}</p>}
            {card.supporting_points && card.supporting_points.length > 0 && (
              <ul className="text-[10px] text-on-surface/50 list-disc pl-3 mt-2 space-y-0.5">
                {card.supporting_points.slice(0, 3).map((line: string) => (
                  <li key={line.slice(0, 40)}>{line}</li>
                ))}
              </ul>
            )}
            {card.uncertainties && card.uncertainties.length > 0 && (
              <ul className="text-[10px] text-amber-200/50 list-disc pl-3 mt-1 space-y-0.5">
                {card.uncertainties.slice(0, 2).map((line: string) => (
                  <li key={line.slice(0, 40)}>{line}</li>
                ))}
              </ul>
            )}
            {card.evidence.length > 0 && (card.supporting_points?.length ?? 0) === 0 && (
              <p className="text-[10px] text-on-surface/40 mt-2 line-clamp-2">{card.evidence[0]}</p>
            )}
            <div className="mt-3 flex flex-wrap gap-1.5">
              <button
                type="button"
                onClick={() => onExpand(batchId, card, index)}
                className="text-xs px-2 py-1 rounded-lg border border-white/10 text-on-surface/80 hover:border-primary/40 hover:text-primary"
                disabled={expandingKey === expandKey}
              >
                {expandingKey === expandKey ? '…' : 'Expand'}
              </button>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function App() {
  const sessionId = useMemo(() => `web-${makeId()}`, [])
  const isDevMode = useMemo(() => {
    if (typeof window === 'undefined') {
      return false
    }
    const devParam = new URLSearchParams(window.location.search).get('dev')
    return devParam === 'true' || devParam === '1'
  }, [])
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'offline'>('checking')
  const [userTurns, setUserTurns] = useState<TranscriptTurn[]>([])
  const [manualTranscriptDraft, setManualTranscriptDraft] = useState('')

  const [recording, setRecording] = useState(false)
  const [transcriptionError, setTranscriptionError] = useState<string | null>(null)
  const [isUploadingChunk, setIsUploadingChunk] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const segmentChunksRef = useRef<Blob[]>([])
  const segmentMimeRef = useRef<string>('audio/webm')
  const uploadQueueRef = useRef<Promise<void>>(Promise.resolve())
  const streamRef = useRef<MediaStream | null>(null)
  const segmentRollTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const continueRecordingRef = useRef(false)
  const recordingStartPerfRef = useRef<number>(0)
  const segmentPerfStartRef = useRef<number>(0)

  const [suggestionBatches, setSuggestionBatches] = useState<StoredSuggestionBatch[]>([])
  const [trajectoryCopyStatus, setTrajectoryCopyStatus] = useState<'idle' | 'ok' | 'err'>('idle')
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [autoRefreshCountdown, setAutoRefreshCountdown] = useState(SUGGESTION_REFRESH_SECONDS)
  const [batchCount, setBatchCount] = useState(0)
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null)
  const [expandingKey, setExpandingKey] = useState<string | null>(null)
  const [transcriptResponseTick, setTranscriptResponseTick] = useState(0)
  const [chatMessages, setChatMessages] = useState<ChatEntry[]>([])
  const [chatDraft, setChatDraft] = useState('')
  const [isSendingChat, setIsSendingChat] = useState(false)

  const refreshQueueRef = useRef<Promise<void>>(Promise.resolve())
  const autoRefreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const mergedTurns = useMemo(
    () => [...userTurns].sort((a, b) => a.start_ms - b.start_ms),
    [userTurns]
  )
  const hasTranscript = mergedTurns.length > 0
  const latest = suggestionBatches[0]

  useEffect(() => {
    getHealth()
      .then(() => setBackendStatus('online'))
      .catch(() => setBackendStatus('offline'))
  }, [])

  const enqueueUpload = useCallback(
    (blob: Blob, startMs: number, endMs: number) => {
      uploadQueueRef.current = uploadQueueRef.current.then(async () => {
        setIsUploadingChunk(true)
        setTranscriptionError(null)
        try {
          const out = await transcribeAudio({
            sessionId,
            startMs,
            endMs,
            audioBlob: blob,
          })
          if (out.turns.length === 0) {
            return
          }
          setUserTurns((prev) => [...prev, ...out.turns])
          setTranscriptResponseTick((prev) => prev + 1)
        } catch (error) {
          const message = error instanceof Error ? error.message : 'Transcription failed'
          setTranscriptionError(message)
        } finally {
          setIsUploadingChunk(false)
        }
      })
    },
    [sessionId]
  )

  const startNextSegment = useCallback(
    (stream: MediaStream) => {
      if (!continueRecordingRef.current) {
        return
      }

      const mimeType = pickAudioMimeType()
      segmentMimeRef.current = mimeType || 'audio/webm'
      const recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream)

      mediaRecorderRef.current = recorder
      segmentChunksRef.current = []
      segmentPerfStartRef.current = performance.now()

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          segmentChunksRef.current.push(event.data)
        }
      }

      recorder.onstop = () => {
        const chunks = segmentChunksRef.current
        segmentChunksRef.current = []

        if (segmentRollTimerRef.current !== null) {
          clearTimeout(segmentRollTimerRef.current)
          segmentRollTimerRef.current = null
        }

        const blob = chunks.length > 0 ? new Blob(chunks, { type: segmentMimeRef.current }) : null

        if (blob && blob.size > 0) {
          const startMs = Math.max(0, Math.floor(segmentPerfStartRef.current - recordingStartPerfRef.current))
          const endMs = Math.max(
            startMs + 1,
            Math.floor(performance.now() - recordingStartPerfRef.current)
          )
          enqueueUpload(blob, startMs, endMs)
        }

        if (continueRecordingRef.current && streamRef.current) {
          startNextSegment(streamRef.current)
        }
      }

      recorder.start()

      segmentRollTimerRef.current = setTimeout(() => {
        if (recorder.state === 'recording') {
          recorder.stop()
        }
      }, TRANSCRIPTION_SEGMENT_MS)
    },
    [enqueueUpload]
  )

  const stopRecording = useCallback(() => {
    continueRecordingRef.current = false
    if (segmentRollTimerRef.current !== null) {
      clearTimeout(segmentRollTimerRef.current)
      segmentRollTimerRef.current = null
    }
    const recorder = mediaRecorderRef.current
    if (recorder && recorder.state !== 'inactive') {
      recorder.stop()
    }
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    mediaRecorderRef.current = null
    setRecording(false)
  }, [])

  const startRecording = useCallback(async () => {
    setTranscriptionError(null)
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      continueRecordingRef.current = true
      recordingStartPerfRef.current = performance.now()
      startNextSegment(stream)
      setRecording(true)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Microphone access failed'
      setTranscriptionError(message)
      setRecording(false)
    }
  }, [startNextSegment])

  const handleToggleRecording = useCallback(() => {
    if (recording) {
      stopRecording()
      return
    }
    void startRecording()
  }, [recording, startRecording, stopRecording])

  useEffect(() => {
    return () => {
      stopRecording()
    }
  }, [stopRecording])

  const appendManualTranscriptTurn = useCallback(() => {
    const text = manualTranscriptDraft.trim()
    if (!text) {
      return
    }
    const nextStartMs = userTurns.length > 0 ? userTurns[userTurns.length - 1].end_ms + 1 : 0
    const turn: TranscriptTurn = {
      id: `manual-${makeId()}`,
      text,
      start_ms: nextStartMs,
      end_ms: nextStartMs + 2000,
      confidence: null,
    }
    setUserTurns((prev) => [...prev, turn])
    setManualTranscriptDraft('')
    setTranscriptResponseTick((prev) => prev + 1)
  }, [manualTranscriptDraft, userTurns])

  const runRefresh = useCallback(
    async (forceRefresh: boolean) => {
      if (!hasTranscript) {
        setRefreshError('Add transcript turns first (mic or manual).')
        return
      }
      setIsRefreshing(true)
      setRefreshError(null)
      try {
        const response = await refreshSuggestions(
          buildRefreshRequest({
            sessionId,
            userTurns,
            forceRefresh,
          })
        )
        setSuggestionBatches((prev) => [
          {
            id: response.batch_key || makeId(),
            createdAt: Date.now(),
            omittedBucket: response.omitted_bucket,
            latencyMs: response.timings.total_ms,
            signalState: response.signal_state,
            scores: response.scores,
            cards: response.cards,
            timings: response.timings,
            metadata: response.metadata ?? {},
          },
          ...prev,
        ])
        setLastLatencyMs(response.timings.total_ms)
        setBatchCount((prev) => prev + 1)
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Refresh failed'
        setRefreshError(message)
      } finally {
        setIsRefreshing(false)
      }
    },
    [hasTranscript, sessionId, userTurns]
  )

  const queueRefresh = useCallback(
    (forceRefresh: boolean) => {
      refreshQueueRef.current = refreshQueueRef.current.then(() => runRefresh(forceRefresh))
      return refreshQueueRef.current
    },
    [runRefresh]
  )

  useEffect(() => {
    if (!recording || !hasTranscript) {
      if (autoRefreshTimerRef.current !== null) {
        clearInterval(autoRefreshTimerRef.current)
        autoRefreshTimerRef.current = null
      }
      setAutoRefreshCountdown(SUGGESTION_REFRESH_SECONDS)
      return
    }

    if (autoRefreshTimerRef.current !== null) {
      clearInterval(autoRefreshTimerRef.current)
    }

    setAutoRefreshCountdown(SUGGESTION_REFRESH_SECONDS)
    autoRefreshTimerRef.current = setInterval(() => {
      setAutoRefreshCountdown((prev) => {
        if (prev <= 1) return SUGGESTION_REFRESH_SECONDS
        return prev - 1
      })
    }, 1000)

    return () => {
      if (autoRefreshTimerRef.current !== null) {
        clearInterval(autoRefreshTimerRef.current)
        autoRefreshTimerRef.current = null
      }
    }
  }, [hasTranscript, recording])

  useEffect(() => {
    if (!recording || !hasTranscript || transcriptResponseTick === 0) {
      return
    }
    setAutoRefreshCountdown(SUGGESTION_REFRESH_SECONDS)
    void queueRefresh(false)
  }, [hasTranscript, queueRefresh, recording, transcriptResponseTick])

  const appendChatMessage = useCallback((entry: Omit<ChatEntry, 'id' | 'at'>) => {
    setChatMessages((prev) => [{ id: makeId(), at: Date.now(), ...entry }, ...prev])
  }, [])

  const handleExpand = useCallback(
    async (batchId: string, card: SuggestionCard, index: number) => {
      const key = `${batchId}-${index}`
      setExpandingKey(key)
      setRefreshError(null)
      try {
        const expanded = await expandSuggestion({
          sessionId,
          clickedCard: card,
        })
        appendChatMessage({ role: 'user', text: card.text })
        appendChatMessage({
          role: 'assistant',
          text: expanded.expanded_text,
          supportingPoints: expanded.supporting_points,
          uncertainties: expanded.uncertainties,
          evidenceUsed: expanded.evidence_used,
        })
        setSuggestionBatches((prev) =>
          prev.map((batch) =>
            batch.id !== batchId
              ? batch
              : {
                  ...batch,
                  cards: batch.cards.map((batchCard, batchCardIndex) =>
                    batchCardIndex === index
                      ? {
                          ...batchCard,
                          text: expanded.expanded_text,
                          evidence: expanded.evidence_used,
                          supporting_points: expanded.supporting_points,
                          uncertainties: expanded.uncertainties,
                        }
                      : batchCard
                  ),
                }
          )
        )
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Expand failed'
        setRefreshError(message)
      } finally {
        setExpandingKey(null)
      }
    },
    [appendChatMessage, sessionId]
  )

  const handleSendChat = useCallback(async () => {
    const message = chatDraft.trim()
    if (!message || isSendingChat) {
      return
    }
    setChatDraft('')
    appendChatMessage({ role: 'user', text: message })
    setIsSendingChat(true)
    setRefreshError(null)
    try {
      const out = await sendChatMessage({ sessionId, message })
      appendChatMessage({
        role: 'assistant',
        text: out.answer,
        supportingPoints: out.supporting_points,
        uncertainties: out.uncertainties,
        evidenceUsed: out.evidence_used,
      })
    } catch (error) {
      const err = error instanceof Error ? error.message : 'Chat failed'
      setRefreshError(err)
      appendChatMessage({
        role: 'assistant',
        text: `Chat failed: ${err}`,
      })
    } finally {
      setIsSendingChat(false)
    }
  }, [appendChatMessage, chatDraft, isSendingChat, sessionId])

  const copyTrajectoryToClipboard = useCallback(async () => {
    const payload = buildTrajectoryJson({
      sessionId,
      transcriptTurns: userTurns,
      suggestionBatches,
    })
    const text = formatTrajectoryJson(payload)
    try {
      await navigator.clipboard.writeText(text)
      setTrajectoryCopyStatus('ok')
      window.setTimeout(() => setTrajectoryCopyStatus('idle'), 2000)
    } catch {
      setTrajectoryCopyStatus('err')
      window.setTimeout(() => setTrajectoryCopyStatus('idle'), 3000)
    }
  }, [sessionId, suggestionBatches, userTurns])

  return (
    <main className="h-screen max-h-screen flex flex-col overflow-hidden max-w-full">
      <div className="flex flex-1 min-h-0 min-w-0">
        <section className="w-full md:w-1/4 md:max-w-[min(28vw,24rem)] border-r border-white/5 flex flex-col bg-surface-container-lowest min-w-0">
          <div className="p-4 sm:p-6 border-b border-white/5">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-on-surface flex items-center gap-1">
                <span className="material-symbols-outlined text-primary">record_voice_over</span>
                Transcript
              </h3>
              <span
                className={`flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded transition-colors duration-300 ${
                  recording ? 'bg-rose-500/20 text-rose-200 ring-1 ring-rose-500/40' : 'bg-white/5 text-white/40'
                }`}
              >
                {recording && (
                  <span
                    className="h-1.5 w-1.5 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse motion-reduce:animate-none"
                    aria-hidden
                  />
                )}
                {recording ? 'LIVE' : 'IDLE'}
              </span>
            </div>
            <div className="mt-2 text-[10px] text-white/30 flex flex-wrap justify-between gap-1">
              <span>API: {backendStatus === 'online' ? 'ok' : backendStatus}</span>
              <span className="truncate" title={sessionId}>
                {sessionId.slice(0, 18)}…
              </span>
            </div>
            <p className="text-[10px] text-white/20 mt-2">WebM segments /api/v1/transcription</p>
            <div className="mt-3 flex flex-wrap gap-2 items-center">
              <button
                type="button"
                onClick={handleToggleRecording}
                aria-pressed={recording}
                className={[
                  'inline-flex items-center gap-2 text-button font-semibold px-4 py-2.5 rounded-xl',
                  'min-w-[9.5rem] justify-center',
                  'transition-all duration-300 ease-out',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0e0e0e] focus-visible:ring-primary/60',
                  recording
                    ? 'bg-rose-600 text-white border-2 border-rose-400/80 shadow-[0_0_0_1px_rgba(251,113,133,0.3),0_4px_24px_rgba(225,29,72,0.45)] hover:bg-rose-500 hover:border-rose-300'
                    : 'active-gradient text-white border-2 border-primary/30 shadow-md shadow-primary/20 hover:shadow-lg hover:shadow-primary/30 hover:border-primary/50',
                ].join(' ')}
              >
                <span
                  className={[
                    'material-symbols-outlined text-[20px] transition-transform duration-300',
                    recording ? 'scale-110 animate-pulse motion-reduce:animate-none' : 'scale-100',
                  ].join(' ')}
                  aria-hidden
                >
                  {recording ? 'stop_circle' : 'mic'}
                </span>
                {recording ? 'Stop' : 'Start'} mic
              </button>
              {transcriptionError && <span className="text-[11px] text-rose-300/90">{transcriptionError}</span>}
            </div>
            {isDevMode && (
              <div className="mt-3 flex flex-col sm:flex-row gap-2">
                <input
                  className="flex-1 w-full min-w-0 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-primary"
                  value={manualTranscriptDraft}
                  onChange={(e) => setManualTranscriptDraft(e.target.value)}
                  placeholder="Dev: paste/type transcript turn + Enter"
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      appendManualTranscriptTurn()
                    }
                  }}
                />
                <button
                  type="button"
                  onClick={appendManualTranscriptTurn}
                  className="text-sm border border-white/10 rounded-lg px-3 py-2 text-on-surface/80 hover:border-primary/40"
                  disabled={!manualTranscriptDraft.trim()}
                >
                  Add
                </button>
              </div>
            )}
            <p className="text-[10px] text-white/20 mt-1">upload: {isUploadingChunk ? 'sending' : 'idle'}</p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 transcript-glow">
            <div className="space-y-4">
              <div className="flex items-center space-x-2">
                <div
                  className="w-8 h-8 rounded-full overflow-hidden border border-primary/20 shrink-0 active-gradient flex items-center justify-center text-button text-white"
                  aria-hidden
                >
                  You
                </div>
                <span className="text-xs font-bold text-primary">Speaker (You)</span>
              </div>
            </div>
            {mergedTurns.length === 0 && <p className="text-on-surface/40 text-sm">No transcript yet.</p>}
            {mergedTurns.map((turn, i) => {
              const age = i < mergedTurns.length - 2
              return (
                <div key={turn.id}>
                  <div className="text-[9px] text-white/20 font-mono">
                    {formatTranscriptTime(turn.start_ms)} – {formatTranscriptTime(turn.end_ms)} · {turn.id.slice(0, 8)}…
                  </div>
                  <p
                    className={`text-body-md leading-relaxed mt-0.5 ${
                      age ? 'text-on-surface/50' : 'text-on-surface/80'
                    } ${i === mergedTurns.length - 1 ? 'text-on-surface/80' : ''}`}
                  >
                    &ldquo;{turn.text}&rdquo;
                    {turn.confidence != null && turn.confidence > 0 && (
                      <span className="ml-1 text-[10px] text-white/25">
                        · {Math.round(turn.confidence * 100)}% conf
                      </span>
                    )}
                  </p>
                </div>
              )
            })}
            {isUploadingChunk && (
              <p className="text-body-md text-on-surface/40 italic">(Transcribing segment...)</p>
            )}
          </div>
        </section>

        <section className="flex-1 flex flex-col bg-background min-w-0 min-h-0">
          <div className="p-4 sm:p-6 border-b border-white/5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold text-on-surface">Live Suggestions</h3>
              <div className="mt-1 flex flex-wrap items-center gap-2 text-[10px] text-white/30">
                {latest?.signalState && (
                  <span
                    className={`px-2 py-0.5 rounded border ${signalPillClass(
                      latest.signalState
                    )} uppercase font-bold tracking-widest text-label-caps`}
                  >
                    signal: {latest.signalState}
                  </span>
                )}
                {latest && <span>omitted: {labelForBucketKey(latest.omittedBucket)}</span>}
                <span>batches: {batchCount}</span>
              </div>
            </div>
            <div className="flex flex-wrap items-center gap-2 sm:gap-3">
              <div className="text-right">
                <div className="text-[10px] text-white/40 uppercase tracking-widest font-bold">Latency</div>
                <div className="text-sm text-primary font-bold">
                  {lastLatencyMs != null ? `${lastLatencyMs}ms` : '—'}
                </div>
              </div>
              <span className="text-[10px] text-white/20">
                {!hasTranscript
                  ? 'need transcript'
                  : recording
                    ? `next auto refresh in ${autoRefreshCountdown}s`
                    : 'mic off (auto paused)'}
              </span>
              <button
                type="button"
                onClick={() => void queueRefresh(true)}
                className="text-sm border border-white/10 rounded-lg px-3 py-1.5 text-on-surface/90 hover:border-primary/40"
                disabled={isRefreshing}
              >
                {isRefreshing ? '…' : 'Reload'}
              </button>
              {isDevMode && (
                <button
                  type="button"
                  onClick={() => void copyTrajectoryToClipboard()}
                  className="text-sm border border-white/10 rounded-lg px-3 py-1.5 text-on-surface/90 hover:border-primary/40"
                  title="Copy JSON"
                >
                  {trajectoryCopyStatus === 'ok' ? 'Copied' : trajectoryCopyStatus === 'err' ? 'Fail' : 'Copy JSON'}
                </button>
              )}
            </div>
          </div>
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-8 min-h-0">
            {refreshError && <p className="text-rose-300/90 text-sm">{refreshError}</p>}

            {suggestionBatches.length === 0 && (
              <p className="text-on-surface/40">Reload (or add transcript) for three cards + scores in the right panel.</p>
            )}

            {latest && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-label-caps text-primary uppercase font-bold tracking-widest">Latest batch</span>
                  <span className="text-[10px] text-white/20">{relTime(latest.createdAt)}</span>
                </div>
                <SuggestionGrid
                  cards={latest.cards}
                  batchId={latest.id}
                  opacity={1}
                  expandingKey={expandingKey}
                  onExpand={handleExpand}
                />
                {latest.timings && (
                  <div className="mt-3 text-[10px] text-white/20 flex flex-wrap gap-x-4 gap-y-0.5 font-mono">
                    <span>state {latest.timings.state_ms}ms</span>
                    <span>llm {latest.timings.llm_main_ms}ms</span>
                    <span>retr {latest.timings.retrieval_ms}ms</span>
                    <span>ver {latest.timings.verify_ms}ms</span>
                    <span>fin {latest.timings.finalize_ms}ms</span>
                  </div>
                )}
              </div>
            )}

            {suggestionBatches.length > 1 && (
              <div>
                <span className="text-label-caps text-white/40 uppercase font-bold tracking-widest block mb-4">
                  Past suggestions
                </span>
                <div className="space-y-8">
                  {suggestionBatches.slice(1).map((batch, bi) => (
                    <div key={batch.id} className="relative pl-1">
                      <div className="absolute -left-1 top-0 bottom-0 w-px bg-white/5" aria-hidden />
                      <div className="flex items-center space-x-2 mb-3">
                        <div
                          className="w-2 h-2 rounded-full bg-white/10 -ml-[0.3rem] shrink-0"
                          aria-hidden
                        />
                        <span className="text-[10px] text-white/20 font-bold uppercase tracking-tight">
                          Batch · {relTime(batch.createdAt)}
                        </span>
                        <span className="text-[10px] text-white/20">omitted {labelForBucketKey(batch.omittedBucket)}</span>
                      </div>
                      <SuggestionGrid
                        cards={batch.cards}
                        batchId={batch.id}
                        opacity={0.4 + 0.25 / (bi + 1)}
                        expandingKey={expandingKey}
                        onExpand={handleExpand}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        <section className="w-full md:w-1/4 md:max-w-[min(28vw,24rem)] border-l border-white/5 flex flex-col bg-surface-container-lowest min-w-0 min-h-0">
          <div className="p-4 sm:p-6 border-b border-white/5">
            <h3 className="text-lg font-semibold text-on-surface flex items-center gap-1">
              <span className="material-symbols-outlined text-primary">smart_toy</span>
              Chat
            </h3>
            <p className="text-[10px] text-white/30 mt-1">
              Click a suggestion or type a question. One continuous chat per session.
            </p>
          </div>
          <div className="flex-1 overflow-y-auto p-4 sm:p-6 space-y-4 min-h-0">
            {latest && (
              <div className="space-y-2">
                <span className="text-[10px] font-bold text-primary uppercase">TwinMind AI</span>
                <div className="glass-card p-4 rounded-xl rounded-tl-none text-sm text-on-surface/80">
                  <p>Latest batch: omitted bucket {labelForBucketKey(latest.omittedBucket)}.</p>
                  {latest.scores && (
                    <ul className="mt-2 text-[12px] text-on-surface/50 space-y-0.5 font-mono">
                      {Object.entries(latest.scores).map(([b, s]) => (
                        <li key={b}>
                          {labelForBucketKey(b)}: {typeof s === 'number' ? s.toFixed(3) : s}
                        </li>
                      ))}
                    </ul>
                  )}
                  {latest.metadata && Object.keys(latest.metadata).length > 0 && (
                    <p className="mt-2 text-[10px] text-white/20">
                      meta: {JSON.stringify(latest.metadata)}
                    </p>
                  )}
                </div>
              </div>
            )}

            {chatMessages.map((msg) => (
              <div key={msg.id} className="space-y-1">
                <div className="text-[10px] font-bold text-white/50 uppercase">
                  {msg.role === 'assistant' ? 'Assistant' : 'You'}
                </div>
                <div
                  className={`glass-card p-3 rounded-lg text-sm ${
                    msg.role === 'assistant' ? 'text-on-surface/85' : 'text-primary/90 border-primary/20'
                  }`}
                >
                  <p>{msg.text}</p>
                  {msg.supportingPoints && msg.supportingPoints.length > 0 && (
                    <ul className="text-[10px] text-on-surface/40 list-disc pl-3 mt-2 space-y-0.5">
                      {msg.supportingPoints.slice(0, 3).map((line) => (
                        <li key={line.slice(0, 32)}>{line}</li>
                      ))}
                    </ul>
                  )}
                  {msg.uncertainties && msg.uncertainties.length > 0 && (
                    <ul className="text-[10px] text-amber-200/50 list-disc pl-3 mt-1 space-y-0.5">
                      {msg.uncertainties.slice(0, 2).map((line) => (
                        <li key={line.slice(0, 32)}>{line}</li>
                      ))}
                    </ul>
                  )}
                  {msg.evidenceUsed && msg.evidenceUsed.length > 0 && (
                    <p className="text-[10px] text-white/25 mt-2 line-clamp-2">{msg.evidenceUsed[0]}</p>
                  )}
                </div>
              </div>
            ))}

            {chatMessages.length === 0 && !latest && (
              <p className="text-sm text-on-surface/30">No chat yet. Click a suggestion or ask directly.</p>
            )}
          </div>
          <div className="p-4 sm:p-6 border-t border-white/5 shrink-0">
            <div className="relative flex gap-2">
              <input
                className="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-primary transition-all"
                value={chatDraft}
                onChange={(e) => setChatDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void handleSendChat()
                  }
                }}
                placeholder="Ask a question..."
                type="text"
              />
              <button
                type="button"
                className="text-sm border border-white/10 rounded-xl px-3 py-2 text-on-surface/90 hover:border-primary/40 disabled:opacity-50"
                onClick={() => void handleSendChat()}
                disabled={!chatDraft.trim() || isSendingChat}
              >
                {isSendingChat ? '…' : 'Send'}
              </button>
            </div>
            {isDevMode && (
              <p className="text-[9px] text-white/20 mt-2">
                Clicked suggestion uses /suggestions/expand. Typed chat uses /chat/message.
              </p>
            )}
          </div>
        </section>
      </div>
    </main>
  )
}

export default App
