import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  expandSuggestion,
  getHealth,
  refreshSuggestions,
  transcribeAudio,
} from './api/client'
import { buildRefreshRequest } from './features/suggestions/buildRefreshRequest'
import {
  buildTrajectoryJson,
  formatTrajectoryJson,
  type StoredSuggestionBatch,
} from './features/trajectory/buildTrajectoryJson'
import type { SuggestionCard, TranscriptTurn } from './types/api'
import './App.css'

/** Each segment is a full WebM file (valid for Groq). Mid-stream blob slices are not. */
const TRANSCRIPTION_SEGMENT_MS = 30_000
const SUGGESTION_REFRESH_SECONDS = 30

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

function formatMs(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const mins = Math.floor(seconds / 60)
  const rem = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`
}

function App() {
  const sessionId = useMemo(() => `web-${makeId()}`, [])
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
  /** performance.now() when user started mic (for elapsed start_ms / end_ms on turns). */
  const recordingStartPerfRef = useRef<number>(0)
  /** performance.now() at current segment MediaRecorder.start() */
  const segmentPerfStartRef = useRef<number>(0)

  const [suggestionBatches, setSuggestionBatches] = useState<StoredSuggestionBatch[]>([])
  const [trajectoryCopyStatus, setTrajectoryCopyStatus] = useState<'idle' | 'ok' | 'err'>('idle')
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [isAutoRefreshEnabled, setIsAutoRefreshEnabled] = useState(true)
  const [autoRefreshCountdown, setAutoRefreshCountdown] = useState(SUGGESTION_REFRESH_SECONDS)
  const [batchCount, setBatchCount] = useState(0)
  const [omittedBucket, setOmittedBucket] = useState<string>('-')
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null)
  const [expandingBucket, setExpandingBucket] = useState<string | null>(null)
  const [transcriptResponseTick, setTranscriptResponseTick] = useState(0)
  const refreshQueueRef = useRef<Promise<void>>(Promise.resolve())
  const autoRefreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const mergedTurns = useMemo(
    () => [...userTurns].sort((a, b) => a.start_ms - b.start_ms),
    [userTurns]
  )
  const hasTranscript = mergedTurns.length > 0

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

  /**
   * One MediaRecorder segment = one valid WebM file (EBML header + clusters).
   * Rolling a new segment every TRANSCRIPTION_SEGMENT_MS avoids invalid fragments.
   */
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

        const blob =
          chunks.length > 0 ? new Blob(chunks, { type: segmentMimeRef.current }) : null

        if (blob && blob.size > 0) {
          const startMs = Math.max(
            0,
            Math.floor(segmentPerfStartRef.current - recordingStartPerfRef.current)
          )
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
          },
          ...prev,
        ])
        setOmittedBucket(response.omitted_bucket)
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
    if (!isAutoRefreshEnabled || !recording || !hasTranscript) {
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
  }, [hasTranscript, isAutoRefreshEnabled, recording])

  useEffect(() => {
    if (!isAutoRefreshEnabled || transcriptResponseTick === 0) {
      return
    }
    setAutoRefreshCountdown(SUGGESTION_REFRESH_SECONDS)
    void queueRefresh(false)
  }, [isAutoRefreshEnabled, queueRefresh, transcriptResponseTick])

  const handleExpand = useCallback(
    async (batchId: string, card: SuggestionCard, index: number) => {
      const key = `${batchId}-${card.bucket}-${index}`
      setExpandingBucket(key)
      setRefreshError(null)
      try {
        const expanded = await expandSuggestion({
          sessionId,
          clickedCard: card,
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
        setExpandingBucket(null)
      }
    },
    [sessionId]
  )

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
    <div className="app-shell">
      <header className="topbar">
        <h1>TwinMind - Live Suggestions</h1>
        <div className="badges">
          <span className={`badge ${backendStatus}`}>
            API: {backendStatus === 'checking' ? 'checking...' : backendStatus}
          </span>
          <span className="badge neutral">session: {sessionId.slice(0, 8)}</span>
        </div>
      </header>

      <main className="cols">
        <section className="panel">
          <div className="panel-header">
            <h2>1. Mic & Transcript</h2>
            <span className={`badge ${recording ? 'recording' : 'idle'}`}>
              {recording ? 'recording' : 'idle'}
            </span>
          </div>
          <div className="panel-body">
            <button className="primary-btn" onClick={handleToggleRecording}>
              {recording ? 'Stop mic' : 'Start mic'}
            </button>
            <p className="hint">
              Records ~{TRANSCRIPTION_SEGMENT_MS / 1000}s WebM segments (valid files) and POSTs to{' '}
              <code>/api/v1/transcription</code>.
            </p>
            <div className="manual-transcript-row">
              <input
                type="text"
                value={manualTranscriptDraft}
                onChange={(event) => setManualTranscriptDraft(event.target.value)}
                placeholder="Type transcript text for testing..."
                onKeyDown={(event) => {
                  if (event.key === 'Enter') {
                    event.preventDefault()
                    appendManualTranscriptTurn()
                  }
                }}
              />
              <button
                className="primary-btn"
                onClick={appendManualTranscriptTurn}
                disabled={!manualTranscriptDraft.trim()}
              >
                Add transcript
              </button>
            </div>

            <div className="status-row">
              <span className="muted">upload:</span>
              <span>{isUploadingChunk ? 'in-flight' : 'idle'}</span>
            </div>
            {transcriptionError && <p className="error">{transcriptionError}</p>}

            <div className="transcript-log">
              {mergedTurns.length === 0 && <p className="muted">No transcript turns yet.</p>}
              {mergedTurns.map((turn) => (
                <article key={turn.id} className="transcript-item">
                  <div className="transcript-meta">
                    <span>{formatMs(turn.start_ms)}</span>
                  </div>
                  <p>{turn.text}</p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="panel">
          <div className="panel-header">
            <h2>2. Live Suggestions</h2>
            <span className="badge neutral">{batchCount} batches</span>
          </div>
          <div className="panel-body">
            <div className="toolbar">
              <button className="primary-btn" onClick={() => void queueRefresh(true)} disabled={isRefreshing}>
                {isRefreshing ? 'Refreshing...' : 'Reload suggestions'}
              </button>
              <button
                type="button"
                className="secondary-btn"
                onClick={() => void copyTrajectoryToClipboard()}
                title="Copy transcript + all suggestion batches as sorted JSON"
              >
                {trajectoryCopyStatus === 'ok' ? 'Copied JSON' : trajectoryCopyStatus === 'err' ? 'Copy failed' : 'Copy trajectory JSON'}
              </button>
              <label className="toggle">
                <input
                  type="checkbox"
                  checked={isAutoRefreshEnabled}
                  onChange={(event) => setIsAutoRefreshEnabled(event.target.checked)}
                />
                auto refresh
              </label>
              <span className="muted">
                {!hasTranscript
                  ? 'waiting for first transcript'
                  : !isAutoRefreshEnabled
                    ? 'paused'
                    : recording
                      ? `in ${autoRefreshCountdown}s (transcript-driven)`
                      : 'mic off'}
              </span>
            </div>

            <div className="status-row">
              <span className="muted">omitted:</span>
              <span>{omittedBucket}</span>
              <span className="muted">latency:</span>
              <span>{lastLatencyMs ?? '-'}ms</span>
            </div>
            {refreshError && <p className="error">{refreshError}</p>}

            <div className="cards">
              {suggestionBatches.length === 0 && <p className="muted">Refresh to get your first 3 cards.</p>}
              {suggestionBatches.map((batch, batchIndex) => (
                <section key={batch.id} className="suggestion-batch">
                  <div className="suggestion-batch-meta">
                    <span>{batchIndex === 0 ? 'latest batch' : `previous #${batchIndex}`}</span>
                    <span>omitted: {batch.omittedBucket}</span>
                    <span>latency: {batch.latencyMs}ms</span>
                  </div>
                  {batch.cards.map((card, index) => {
                    const expandKey = `${batch.id}-${card.bucket}-${index}`
                    return (
                      <article key={expandKey} className="suggestion-card">
                        <header>
                          <span className="bucket">{card.bucket.replace('_', ' ')}</span>
                          <span className="confidence">{Math.round(card.confidence * 100)}%</span>
                        </header>
                        <p>{card.text}</p>
                        <footer>
                          <button
                            onClick={() => void handleExpand(batch.id, card, index)}
                            disabled={expandingBucket === expandKey}
                          >
                            {expandingBucket === expandKey ? 'Expanding...' : 'Expand'}
                          </button>
                        </footer>
                      </article>
                    )
                  })}
                </section>
              ))}
            </div>
          </div>
        </section>

        <section className="panel panel-disabled">
          <div className="panel-header">
            <h2>3. Chat (next)</h2>
            <span className="badge neutral">pending</span>
          </div>
          <div className="panel-body">
            <p className="muted">Out of scope in this pass. First two columns are functional.</p>
          </div>
        </section>
      </main>
    </div>
  )
}

export default App
