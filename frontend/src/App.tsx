import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  exportSession,
  expandSuggestion,
  getHealth,
  getRuntimeSettings,
  refreshSuggestions,
  sendChatMessage,
  transcribeAudio,
  updateRuntimeApiKey,
  updateRuntimeSettings,
} from './api/client'
import { buildRefreshRequest } from './features/suggestions/buildRefreshRequest'
import { bucketUi, formatTranscriptTime, labelForBucketKey, relTime } from './features/dashboard/stitchUtils'
import { type StoredSuggestionBatch } from './features/trajectory/buildTrajectoryJson'
import type { RuntimeSettings, SignalState, SuggestionCard, TranscriptTurn } from './types/api'

const TRANSCRIPTION_SEGMENT_MS = 30_000
const SUGGESTION_REFRESH_SECONDS = 30
const API_KEY_STORAGE_KEY = 'twinmind_runtime_groq_api_key'

const DEFAULT_RUNTIME_SETTINGS: RuntimeSettings = {
  live_prompt: 'rank_and_draft_v1',
  fact_check_prompt: 'verify_factcheck_v1',
  expand_prompt: 'expand_v1',
  chat_prompt: 'chat_v1',
  live_prompt_template: '',
  fact_check_prompt_template: '',
  expand_prompt_template: '',
  chat_prompt_template: '',
  context_window_turns: 12,
  expand_context_window_turns: 24,
  chat_context_window_turns: 24,
  chat_history_window_messages: 12,
  fact_check_score_threshold: 0.65,
  enable_conditional_web: true,
}

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

function formatCountdown(seconds: number): string {
  const safeSeconds = Math.max(0, seconds)
  const mins = Math.floor(safeSeconds / 60)
  const secs = safeSeconds % 60
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`
}

function signalPillClass(state: SignalState | undefined): string {
  if (state === 'urgent') return 'text-red-200 border border-red-500/50 bg-red-500/15'
  if (state === 'weak') return 'text-slate-200/90 border border-slate-500/40 bg-slate-500/15'
  return 'text-primary border border-primary/45 bg-primary/15'
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
  /** Which card (batchId-index) is opening detail in chat, if any. */
  detailLoadingKey: string | null
  onOpenInChat: (batchId: string, card: SuggestionCard, index: number) => void
}

function SuggestionGrid({
  cards,
  batchId,
  opacity,
  detailLoadingKey,
  onOpenInChat,
}: SuggestionGridProps) {
  return (
    <div
      className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-sm transition-opacity"
      style={{ opacity }}
    >
      {cards.map((card, index) => {
        const ui = bucketUi(card.bucket)
        const loadKey = `${batchId}-${index}`
        const busy = detailLoadingKey === loadKey
        return (
          <div
            key={loadKey}
            role="button"
            tabIndex={0}
            onClick={() => onOpenInChat(batchId, card, index)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                onOpenInChat(batchId, card, index)
              }
            }}
            className={`glass-card p-sm rounded-xl ${ui.borderClass} group flex flex-col min-h-0 min-w-0 text-left
              cursor-pointer select-none
              transition-[box-shadow,ring] duration-200
              hover:ring-2 hover:ring-primary/35 focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary/50 focus-visible:outline-offset-2
              ${busy ? 'ring-2 ring-primary/50 opacity-90 pointer-events-none' : ''}`}
          >
            <div className="flex justify-between items-start gap-1 mb-2">
              <div className="flex flex-col gap-1 min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span
                    className={`shrink-0 ${ui.tagClass} text-[10px] font-bold px-2 py-0.5 rounded-full uppercase leading-tight`}
                  >
                    {ui.label}
                  </span>
                  {card.confidence > 0 && (
                    <span className="text-[10px] text-on-surface/60 tabular-nums" title="Model score for this card">
                      {Math.round(card.confidence * 100)}%
                    </span>
                  )}
                  {card.verdict && (
                    <span className={`text-[10px] font-semibold ${verdictPill(card.verdict)}`}>
                      {card.verdict}
                    </span>
                  )}
                </div>
                <p className="text-sm text-on-surface/95 font-medium leading-relaxed break-words whitespace-pre-wrap max-h-[min(42vh,22rem)] overflow-y-auto pr-0.5">
                  {card.text}
                </p>
                {card.evidence.length > 0 && (
                  <p className="text-[10px] text-on-surface/60 mt-1.5 break-words border-t border-white/10 pt-1.5">
                    {card.evidence[0]}
                  </p>
                )}
              </div>
              <span
                className={`material-symbols-outlined text-on-surface/45 text-lg shrink-0 ${
                  card.bucket === 'fact_check' ? 'text-orange-400/70' : ''
                }`}
                aria-hidden
              >
                {busy ? 'hourglass_empty' : 'chat'}
              </span>
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
  const [contextNotesDraft, setContextNotesDraft] = useState('')

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
  const [exportStatus, setExportStatus] = useState<'idle' | 'ok' | 'err'>('idle')
  const [isExporting, setIsExporting] = useState(false)
  const [refreshError, setRefreshError] = useState<string | null>(null)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [autoRefreshCountdown, setAutoRefreshCountdown] = useState(SUGGESTION_REFRESH_SECONDS)
  const [batchCount, setBatchCount] = useState(0)
  const [lastLatencyMs, setLastLatencyMs] = useState<number | null>(null)
  const [suggestionDetailKey, setSuggestionDetailKey] = useState<string | null>(null)
  const suggestionDetailInFlight = useRef(false)
  const chatThreadRef = useRef<HTMLDivElement>(null)
  const chatColumnRef = useRef<HTMLElement>(null)
  const [transcriptResponseTick, setTranscriptResponseTick] = useState(0)
  const [chatMessages, setChatMessages] = useState<ChatEntry[]>([])
  const [chatDraft, setChatDraft] = useState('')
  const [isSendingChat, setIsSendingChat] = useState(false)
  const [runtimeSettings, setRuntimeSettings] = useState<RuntimeSettings>(DEFAULT_RUNTIME_SETTINGS)
  const [settingsDraft, setSettingsDraft] = useState<RuntimeSettings>(DEFAULT_RUNTIME_SETTINGS)
  const [settingsModalOpen, setSettingsModalOpen] = useState(false)
  const [isSavingSettings, setIsSavingSettings] = useState(false)
  const [settingsError, setSettingsError] = useState<string | null>(null)
  const [settingsSuccess, setSettingsSuccess] = useState<string | null>(null)
  const [apiKeyDraft, setApiKeyDraft] = useState('')
  const [rememberApiKey, setRememberApiKey] = useState(true)
  const [apiKeySource, setApiKeySource] = useState<'runtime' | 'env' | 'none'>('none')

  const refreshQueueRef = useRef<Promise<void>>(Promise.resolve())
  const autoRefreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const transcriptListRef = useRef<HTMLDivElement>(null)

  const mergedTurns = useMemo(
    () => [...userTurns].sort((a, b) => a.start_ms - b.start_ms),
    [userTurns]
  )
  const hasTranscript = mergedTurns.length > 0
  const latest = suggestionBatches[0]

  useEffect(() => {
    const el = transcriptListRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [mergedTurns.length, isUploadingChunk])

  useEffect(() => {
    getHealth()
      .then(() => setBackendStatus('online'))
      .catch(() => setBackendStatus('offline'))
  }, [])

  useEffect(() => {
    let cancelled = false

    const hydrateRuntimeSettings = async () => {
      const storedApiKey = window.localStorage.getItem(API_KEY_STORAGE_KEY) ?? ''
      if (storedApiKey) {
        setApiKeyDraft(storedApiKey)
      }

      try {
        const settingsEnvelope = await getRuntimeSettings()
        if (cancelled) return
        setRuntimeSettings(settingsEnvelope.settings)
        setSettingsDraft(settingsEnvelope.settings)

        // Always sync local key to backend runtime on app start.
        // Empty local key clears runtime key so backend falls back to env key.
        const runtimeStatus = await updateRuntimeApiKey(storedApiKey)
        if (cancelled) return
        setApiKeySource(runtimeStatus.source)
      } catch (error) {
        if (cancelled) return
        const message = error instanceof Error ? error.message : 'Failed to load runtime settings'
        setSettingsError(message)
      }
    }

    void hydrateRuntimeSettings()
    return () => {
      cancelled = true
    }
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
            contextWindowTurns: runtimeSettings.context_window_turns,
            enableConditionalWeb: runtimeSettings.enable_conditional_web,
            approvedSources: contextNotesDraft
              .split('\n')
              .map((line) => line.trim())
              .filter(Boolean),
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
    [
      contextNotesDraft,
      hasTranscript,
      runtimeSettings.context_window_turns,
      runtimeSettings.enable_conditional_web,
      sessionId,
      userTurns,
    ]
  )

  const queueRefresh = useCallback(
    (forceRefresh: boolean) => {
      refreshQueueRef.current = refreshQueueRef.current.then(() => runRefresh(forceRefresh))
      return refreshQueueRef.current
    },
    [runRefresh]
  )

  useEffect(() => {
    if (!recording) {
      if (autoRefreshTimerRef.current !== null) {
        clearInterval(autoRefreshTimerRef.current)
        autoRefreshTimerRef.current = null
      }
      return
    }

    if (autoRefreshTimerRef.current !== null) {
      clearInterval(autoRefreshTimerRef.current)
    }

    setAutoRefreshCountdown(SUGGESTION_REFRESH_SECONDS)
    autoRefreshTimerRef.current = setInterval(() => {
      setAutoRefreshCountdown((prev) => (prev <= 0 ? 0 : prev - 1))
    }, 1000)

    return () => {
      if (autoRefreshTimerRef.current !== null) {
        clearInterval(autoRefreshTimerRef.current)
        autoRefreshTimerRef.current = null
      }
    }
  }, [recording])

  useEffect(() => {
    if (transcriptResponseTick === 0 || !hasTranscript) {
      return
    }
    // Transcript response is the trigger for suggestions refresh.
    setAutoRefreshCountdown(SUGGESTION_REFRESH_SECONDS)
    void queueRefresh(false)
  }, [hasTranscript, queueRefresh, transcriptResponseTick])

  const handleSaveSettings = useCallback(async () => {
    setSettingsError(null)
    setSettingsSuccess(null)
    setIsSavingSettings(true)
    try {
      const trimmedApiKey = apiKeyDraft.trim()
      await updateRuntimeSettings(settingsDraft)
      await updateRuntimeApiKey(trimmedApiKey)
      if (rememberApiKey) {
        window.localStorage.setItem(API_KEY_STORAGE_KEY, trimmedApiKey)
      } else {
        window.localStorage.removeItem(API_KEY_STORAGE_KEY)
      }
      setRuntimeSettings(settingsDraft)
      setApiKeySource(trimmedApiKey ? 'runtime' : 'env')
      setSettingsSuccess('Settings saved')
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save settings'
      setSettingsError(message)
    } finally {
      setIsSavingSettings(false)
    }
  }, [apiKeyDraft, rememberApiKey, settingsDraft])

  const appendChatMessage = useCallback((entry: Omit<ChatEntry, 'id' | 'at'>) => {
    setChatMessages((prev) => [...prev, { id: makeId(), at: Date.now(), ...entry }])
  }, [])

  useEffect(() => {
    const el = chatThreadRef.current
    if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
  }, [chatMessages, isSendingChat, suggestionDetailKey])

  const handleOpenSuggestionInChat = useCallback(
    async (batchId: string, card: SuggestionCard, index: number) => {
      if (suggestionDetailInFlight.current) {
        return
      }
      const key = `${batchId}-${index}`
      setRefreshError(null)
      suggestionDetailInFlight.current = true
      setSuggestionDetailKey(key)

      /** Assignment: add suggestion to chat, then long-form answer via expand (full transcript in backend). */
      appendChatMessage({ role: 'user', text: card.text })
      queueMicrotask(() => {
        chatColumnRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      })

      try {
        const expanded = await expandSuggestion({
          sessionId,
          clickedCard: card,
        })
        appendChatMessage({
          role: 'assistant',
          text: expanded.expanded_text,
          supportingPoints: expanded.supporting_points,
          uncertainties: expanded.uncertainties,
          evidenceUsed: expanded.evidence_used,
        })
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Request failed'
        setRefreshError(message)
        appendChatMessage({
          role: 'assistant',
          text: `Couldn’t load a detailed answer. (${message})`,
        })
      } finally {
        suggestionDetailInFlight.current = false
        setSuggestionDetailKey(null)
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

  const downloadSessionExport = useCallback(async () => {
    setIsExporting(true)
    try {
      const out = await exportSession(sessionId, 'json')
      const payloadText =
        typeof out.content === 'string' ? out.content : `${JSON.stringify(out.content, null, 2)}\n`
      const blob = new Blob([payloadText], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const safeSessionId = sessionId.replace(/[^a-zA-Z0-9_-]/g, '_')
      const stamp = out.exported_at.replace(/[:.]/g, '-')
      const filename = `twinmind-export-${safeSessionId}-${stamp}.json`
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
      setExportStatus('ok')
      window.setTimeout(() => setExportStatus('idle'), 2000)
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Export failed'
      setRefreshError(message)
      setExportStatus('err')
      window.setTimeout(() => setExportStatus('idle'), 3000)
    } finally {
      setIsExporting(false)
    }
  }, [sessionId])

  return (
    <main className="h-screen max-h-screen flex flex-col overflow-hidden max-w-full">
      <div className="flex flex-1 min-h-0 min-w-0">
        <section className="w-full md:w-1/4 md:max-w-[min(28vw,24rem)] ui-column-rule-r flex flex-col bg-surface-container-lowest min-w-0 min-h-0">
          <div className="px-4 sm:px-6 py-3 ui-section-header shrink-0">
            <div className="flex items-center justify-between gap-3 min-h-[3rem]">
              <div className="flex items-center gap-2 min-w-0 flex-wrap">
                <h3 className="text-lg font-semibold text-on-surface flex items-center gap-1 shrink-0">
                  <span className="material-symbols-outlined text-primary text-[22px]">record_voice_over</span>
                  Transcript
                </h3>
                <span
                  className={`flex items-center gap-1.5 text-[10px] font-bold px-2 py-1 rounded transition-colors duration-300 shrink-0 ${
                    recording
                      ? 'bg-rose-500/20 text-rose-100 ring-1 ring-rose-500/50'
                      : 'bg-white/10 text-on-surface/80 border border-white/15'
                  }`}
                >
                  {recording && (
                    <span
                      className="h-1.5 w-1.5 rounded-full bg-rose-500 shadow-[0_0_8px_#f43f5e] animate-pulse motion-reduce:animate-none"
                      aria-hidden
                    />
                  )}
                  {recording ? 'LIVE' : 'Ready'}
                </span>
              </div>
              <button
                type="button"
                onClick={handleToggleRecording}
                aria-pressed={recording}
                className={[
                  'inline-flex items-center gap-1.5 text-sm font-semibold px-3 py-2 rounded-lg shrink-0',
                  'h-10 transition-all duration-300 ease-out',
                  'focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0e0e0e] focus-visible:ring-primary/60',
                  recording
                    ? 'bg-rose-600 text-white border-2 border-rose-400/80 shadow-[0_0_0_1px_rgba(251,113,133,0.3),0_4px_24px_rgba(225,29,72,0.45)] hover:bg-rose-500 hover:border-rose-300'
                    : 'active-gradient text-white border-2 border-primary/30 shadow-md shadow-primary/20 hover:shadow-lg hover:shadow-primary/30 hover:border-primary/50',
                ].join(' ')}
              >
                <span
                  className={[
                    'material-symbols-outlined text-[18px] transition-transform duration-300',
                    recording ? 'scale-110 animate-pulse motion-reduce:animate-none' : 'scale-100',
                  ].join(' ')}
                  aria-hidden
                >
                  {recording ? 'stop_circle' : 'mic'}
                </span>
                {recording ? 'Stop' : 'Start'} mic
              </button>
            </div>
          </div>
          <div
            ref={transcriptListRef}
            className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 sm:py-6 space-y-4 transcript-glow min-h-0"
          >
            {isDevMode && (
              <div className="text-[10px] text-on-surface/55 space-y-1 pb-2 border-b border-white/10">
                <div className="flex flex-wrap justify-between gap-1">
                  <span>API: {backendStatus === 'online' ? 'ok' : backendStatus}</span>
                  <span className="truncate font-mono max-w-[10rem]" title={sessionId}>
                    {sessionId.slice(0, 12)}…
                  </span>
                </div>
                <p className="font-mono">POST /api/v1/transcription · WebM</p>
                <p>
                  upload queue: {isUploadingChunk ? 'sending' : 'idle'}
                </p>
                <div className="flex flex-col sm:flex-row gap-2 pt-1">
                  <input
                    className="flex-1 w-full min-w-0 bg-white/[0.07] border-2 border-white/20 rounded-lg px-3 py-2 text-sm text-on-surface/95 placeholder:text-on-surface/45 focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30"
                    value={manualTranscriptDraft}
                    onChange={(e) => setManualTranscriptDraft(e.target.value)}
                    placeholder="Dev: paste/type turn + Enter"
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
                    className="ui-btn ui-btn-ghost text-sm rounded-lg px-3.5 py-2 shrink-0"
                    disabled={!manualTranscriptDraft.trim()}
                  >
                    Add
                  </button>
                </div>
              </div>
            )}
            <div className="pb-2 border-b border-white/10 space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[10px] text-on-surface/60 uppercase tracking-wide font-semibold">
                  Context Notes
                </span>
                <span className="text-[10px] text-on-surface/45">sent with next refresh</span>
              </div>
              <textarea
                value={contextNotesDraft}
                onChange={(e) => setContextNotesDraft(e.target.value)}
                placeholder="Optional context lines (one per line)"
                className="w-full min-h-16 bg-white/[0.07] border border-white/20 rounded-lg px-3 py-2 text-xs text-on-surface/95 placeholder:text-on-surface/45 focus:outline-none focus:border-primary/60"
              />
            </div>
            {transcriptionError && <p className="text-[11px] text-rose-300/90">{transcriptionError}</p>}
            {mergedTurns.length === 0 && (
              <p className="text-on-surface/70 text-sm">Start the mic to capture what you say.</p>
            )}
            {mergedTurns.map((turn, i) => {
              const age = i < mergedTurns.length - 2
              return (
                <div key={turn.id}>
                  <div
                    className="text-[9px] text-on-surface/55 font-mono"
                    title={isDevMode ? turn.id : undefined}
                  >
                    {formatTranscriptTime(turn.start_ms)} – {formatTranscriptTime(turn.end_ms)}
                    {isDevMode ? ` · ${turn.id.slice(0, 8)}…` : null}
                  </div>
                  <p
                    className={`text-body-md leading-relaxed ${mergedTurns.length > 0 ? 'mt-0.5' : ''} ${
                      age ? 'text-on-surface/70' : 'text-on-surface/95'
                    } ${i === mergedTurns.length - 1 ? 'text-on-surface/95' : ''}`}
                  >
                    &ldquo;{turn.text}&rdquo;
                    {isDevMode && turn.confidence != null && turn.confidence > 0 && (
                      <span className="ml-1 text-[10px] text-on-surface/50">
                        · {Math.round(turn.confidence * 100)}%
                      </span>
                    )}
                  </p>
                </div>
              )
            })}
            {isUploadingChunk && (recording || mergedTurns.length > 0) && (
              <p className="text-sm text-on-surface/70 italic">Transcribing…</p>
            )}
          </div>
        </section>

        <section className="flex-1 flex flex-col bg-background min-w-0 min-h-0">
          <div className="px-4 sm:px-6 py-3 ui-section-header shrink-0">
            <div className="flex items-center justify-between gap-3 min-h-[3rem]">
              <div className="flex items-center gap-2 min-w-0 flex-1 flex-wrap">
                <h3 className="text-lg font-semibold text-on-surface shrink-0">Live Suggestions</h3>
                {latest?.signalState === 'urgent' && (
                  <span
                    className="px-2 py-0.5 rounded border text-red-200 border-red-500/50 bg-red-500/15 text-[10px] font-bold uppercase tracking-wide shrink-0"
                    title="Model thinks this is a high-stakes moment"
                  >
                    High stakes
                  </span>
                )}
                {latest?.signalState === 'weak' && (
                  <span
                    className="px-2 py-0.5 rounded border text-slate-200 border-slate-500/40 bg-slate-500/15 text-[10px] font-bold uppercase tracking-wide shrink-0"
                    title="Lighter moment in the conversation"
                  >
                    Soft moment
                  </span>
                )}
              </div>
              <div className="flex flex-wrap items-center justify-end gap-2 sm:gap-3 shrink-0">
                <div className="text-right" title="Round-trip time for the last suggestion refresh">
                  <div className="text-[10px] text-on-surface/55 uppercase tracking-widest font-semibold leading-tight">
                    Latency
                  </div>
                  <div className="text-sm text-primary font-bold tabular-nums leading-tight">
                    {lastLatencyMs != null ? `${lastLatencyMs}ms` : '—'}
                  </div>
                </div>
                {(recording || hasTranscript) && (
                  <span
                    className="text-[10px] text-on-surface/55 max-w-[10rem] sm:max-w-none text-right"
                    title="Auto-refresh runs every 30s of active transcript time"
                  >
                    {recording
                      ? hasTranscript
                        ? `Next API call in ${formatCountdown(autoRefreshCountdown)}`
                        : `Next API call after transcript (${formatCountdown(autoRefreshCountdown)})`
                      : `Next API call paused (${formatCountdown(autoRefreshCountdown)})`}
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => void queueRefresh(true)}
                  className="ui-btn text-sm rounded-lg px-3.5 py-2 h-10"
                  disabled={isRefreshing}
                >
                  {isRefreshing ? '…' : 'Refresh'}
                </button>
                <button
                  type="button"
                  onClick={() => void downloadSessionExport()}
                  className="ui-btn ui-btn-ghost text-sm rounded-lg px-3.5 py-2 h-10"
                  title="Download full session JSON export"
                  disabled={isExporting}
                >
                  {isExporting ? 'Exporting…' : exportStatus === 'ok' ? 'Downloaded' : exportStatus === 'err' ? 'Fail' : 'Export'}
                </button>
              </div>
            </div>
          </div>
          <div className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 sm:py-6 space-y-8 min-h-0">
            {isDevMode && latest && (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-on-surface/55 pb-2 border-b border-white/10">
                {latest.signalState === 'normal' && (
                  <span
                    className={`px-2 py-0.5 rounded border ${signalPillClass(
                      latest.signalState
                    )} font-bold uppercase tracking-wider`}
                  >
                    signal: {latest.signalState}
                  </span>
                )}
                <span title="Bucket not in this round of three">
                  not shown: {labelForBucketKey(latest.omittedBucket)}
                </span>
                <span>updates: {batchCount}</span>
              </div>
            )}
            {refreshError && <p className="text-rose-300/90 text-sm">{refreshError}</p>}

            {suggestionBatches.length === 0 && (
              <p className="text-on-surface/70">
                {hasTranscript
                  ? 'Loading suggestions, or press Refresh if nothing appears.'
                  : 'Turn the mic on and speak—suggestions will show here.'}
              </p>
            )}

            {latest && (
              <div>
                <div className="flex items-center justify-between mb-3">
                  <span className="text-label-caps text-primary uppercase font-bold tracking-widest">Latest</span>
                  <span className="text-[10px] text-on-surface/55" title="When this set was created">
                    {relTime(latest.createdAt)}
                  </span>
                </div>
                <SuggestionGrid
                  cards={latest.cards}
                  batchId={latest.id}
                  opacity={1}
                  detailLoadingKey={suggestionDetailKey}
                  onOpenInChat={handleOpenSuggestionInChat}
                />
                {isDevMode && latest.timings && (
                  <div className="mt-3 text-[10px] text-on-surface/55 flex flex-wrap gap-x-3 gap-y-0.5 font-mono">
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
                <span className="text-label-caps text-on-surface/75 uppercase font-bold tracking-widest block mb-4">
                  Earlier
                </span>
                <div className="space-y-8">
                  {suggestionBatches.slice(1).map((batch, bi) => (
                    <div key={batch.id} className="relative pl-1">
                      <div
                        className="absolute -left-1 top-0 bottom-0 w-[2px] rounded-full bg-primary/40"
                        aria-hidden
                      />
                      <div className="flex items-center space-x-2 mb-3">
                        <div
                          className="w-2.5 h-2.5 rounded-full bg-primary/60 ring-1 ring-primary/30 -ml-[0.3rem] shrink-0"
                          aria-hidden
                        />
                        <span className="text-[10px] text-on-surface/70 font-bold uppercase tracking-tight">
                          {relTime(batch.createdAt)}
                        </span>
                        {isDevMode && (
                          <span
                            className="text-[10px] text-on-surface/50"
                            title="Bucket not shown in this round"
                          >
                            not shown: {labelForBucketKey(batch.omittedBucket)}
                          </span>
                        )}
                      </div>
                      <SuggestionGrid
                        cards={batch.cards}
                        batchId={batch.id}
                        opacity={0.4 + 0.25 / (bi + 1)}
                        detailLoadingKey={suggestionDetailKey}
                        onOpenInChat={handleOpenSuggestionInChat}
                      />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </section>

        <section
          ref={chatColumnRef}
          className="w-full md:w-1/4 md:max-w-[min(28vw,24rem)] ui-column-rule-l flex flex-col bg-surface-container-lowest min-w-0 min-h-0"
        >
          <div className="px-4 sm:px-6 py-3 ui-section-header shrink-0">
            <div className="flex items-center justify-between gap-3 min-h-[3rem]">
              <h3 className="text-lg font-semibold text-on-surface flex items-center gap-1 min-w-0">
                <span className="material-symbols-outlined text-primary text-[22px] shrink-0">smart_toy</span>
                Chat
              </h3>
            </div>
          </div>
          <div
            ref={chatThreadRef}
            className="flex-1 overflow-y-auto px-4 sm:px-6 py-4 sm:py-6 space-y-4 min-h-0"
          >
            <p className="text-[10px] text-on-surface/60 leading-snug">
              Tap a suggestion card for a detailed answer, or type at the bottom.
            </p>
            {isDevMode && latest && (
              <div className="space-y-2">
                <span className="text-[10px] font-bold text-primary uppercase">Debug · last batch</span>
                <div className="glass-card p-4 rounded-xl rounded-tl-none text-sm text-on-surface/90">
                  <p className="text-on-surface/80">
                    Not in top 3: <span className="font-medium">{labelForBucketKey(latest.omittedBucket)}</span>
                  </p>
                  {latest.scores && (
                    <ul className="mt-2 text-[12px] text-on-surface/65 space-y-0.5 font-mono">
                      {Object.entries(latest.scores).map(([b, s]) => (
                        <li key={b}>
                          {labelForBucketKey(b)}: {typeof s === 'number' ? s.toFixed(3) : s}
                        </li>
                      ))}
                    </ul>
                  )}
                  {latest.metadata && Object.keys(latest.metadata).length > 0 && (
                    <p className="mt-2 text-[10px] text-on-surface/50 break-all font-mono">
                      {JSON.stringify(latest.metadata)}
                    </p>
                  )}
                </div>
              </div>
            )}

            {chatMessages.map((msg) => (
              <div key={msg.id} className="space-y-1">
                <div className="text-[10px] font-bold text-on-surface/80 uppercase">
                  {msg.role === 'assistant' ? 'Assistant' : 'You'}
                </div>
                <div
                  className={`glass-card p-3 rounded-lg text-sm ${
                    msg.role === 'assistant' ? 'text-on-surface/90' : 'text-primary/95 border-2 border-primary/35'
                  }`}
                >
                  <p className="whitespace-pre-wrap break-words">{msg.text}</p>
                  {msg.supportingPoints && msg.supportingPoints.length > 0 && (
                    <ul className="text-[10px] text-on-surface/70 list-disc pl-3 mt-2 space-y-0.5">
                      {msg.supportingPoints.slice(0, 3).map((line) => (
                        <li key={line.slice(0, 32)}>{line}</li>
                      ))}
                    </ul>
                  )}
                  {msg.uncertainties && msg.uncertainties.length > 0 && (
                    <ul className="text-[10px] text-amber-200/80 list-disc pl-3 mt-1 space-y-0.5">
                      {msg.uncertainties.slice(0, 2).map((line) => (
                        <li key={line.slice(0, 32)}>{line}</li>
                      ))}
                    </ul>
                  )}
                  {msg.evidenceUsed && msg.evidenceUsed.length > 0 && (
                    <p className="text-[10px] text-on-surface/60 mt-2 break-words whitespace-pre-wrap">
                      {msg.evidenceUsed[0]}
                    </p>
                  )}
                </div>
              </div>
            ))}

            {chatMessages.length === 0 && <p className="text-sm text-on-surface/65">No messages yet.</p>}
          </div>
          <div className="px-4 sm:px-6 py-4 border-t border-white/20 shrink-0 bg-black/20">
            <div className="relative flex gap-2">
              <input
                className="w-full bg-white/[0.08] border-2 border-white/20 rounded-xl px-4 py-3 text-sm text-on-surface/95 placeholder:text-on-surface/50 focus:outline-none focus:border-primary/60 focus:ring-1 focus:ring-primary/30 transition-all"
                value={chatDraft}
                onChange={(e) => setChatDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    void handleSendChat()
                  }
                }}
                placeholder="Type a follow-up…"
                type="text"
              />
              <button
                type="button"
                className="ui-btn text-sm rounded-xl px-4 py-2.5 shrink-0"
                onClick={() => void handleSendChat()}
                disabled={!chatDraft.trim() || isSendingChat}
              >
                {isSendingChat ? '…' : 'Send'}
              </button>
            </div>
            {isDevMode && (
              <p className="text-[9px] text-on-surface/55 mt-2">
                Suggestion: POST /suggestions/expand. Typed line: POST /chat/message.
              </p>
            )}
          </div>
        </section>
      </div>
      <button
        type="button"
        aria-label="Open settings"
        onClick={() => {
          setSettingsDraft(runtimeSettings)
          setSettingsModalOpen(true)
          setSettingsError(null)
          setSettingsSuccess(null)
        }}
        className="fixed right-0 top-1/2 -translate-y-1/2 translate-x-[22%] z-20 h-16 w-14 rounded-l-2xl border-2 border-r-0 border-primary/55 bg-surface-container-lowest/98 text-primary shadow-[0_6px_20px_rgba(0,0,0,0.5),0_0_0_1px_rgba(173,198,255,0.35)] backdrop-blur hover:border-primary hover:text-[#d8e7ff] hover:shadow-[0_10px_26px_rgba(0,0,0,0.55),0_0_16px_rgba(173,198,255,0.45)] transition-all flex items-center justify-center"
      >
        <span className="material-symbols-outlined text-[24px] leading-none drop-shadow-[0_0_8px_rgba(173,198,255,0.45)]" aria-hidden>
          settings
        </span>
      </button>
      {settingsModalOpen && (
        <div className="fixed inset-0 z-30 bg-black/55 backdrop-blur-[2px] flex items-center justify-center p-4">
          <div className="w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-2xl border border-white/15 bg-surface-container-lowest p-5 sm:p-6 space-y-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-lg font-semibold text-on-surface">Runtime Settings</h3>
              <button
                type="button"
                onClick={() => setSettingsModalOpen(false)}
                className="ui-btn ui-btn-ghost text-sm rounded-lg px-3 py-2"
              >
                Close
              </button>
            </div>
            <p className="text-xs text-on-surface/70">
              API key is stored in browser localStorage (optional) and sent to backend runtime memory. It is not persisted
              server-side across backend restarts.
            </p>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-on-surface/70">Groq API key</span>
                <input
                  type="password"
                  value={apiKeyDraft}
                  onChange={(e) => setApiKeyDraft(e.target.value)}
                  placeholder="gsk_..."
                  className="w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-sm text-on-surface/95 focus:outline-none focus:border-primary/60"
                />
              </label>
              <div className="text-xs text-on-surface/70 self-end pb-1">
                Active key source: <span className="font-semibold">{apiKeySource}</span>
              </div>
            </div>
            <label className="inline-flex items-center gap-2 text-xs text-on-surface/80">
              <input
                type="checkbox"
                checked={rememberApiKey}
                onChange={(e) => setRememberApiKey(e.target.checked)}
              />
              Remember API key in this browser
            </label>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-xs text-on-surface/70">Live context window turns</span>
                <input
                  type="number"
                  min={1}
                  max={80}
                  value={settingsDraft.context_window_turns}
                  onChange={(e) =>
                    setSettingsDraft((prev) => ({ ...prev, context_window_turns: Number(e.target.value) || 1 }))
                  }
                  className="w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-sm text-on-surface/95 focus:outline-none focus:border-primary/60"
                />
                <span className="text-[11px] text-on-surface/55 leading-snug">
                  How many latest transcript turns are sent when generating live suggestion cards.
                </span>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-xs text-on-surface/70">Expand context window turns</span>
                <input
                  type="number"
                  min={1}
                  max={200}
                  value={settingsDraft.expand_context_window_turns}
                  onChange={(e) =>
                    setSettingsDraft((prev) => ({
                      ...prev,
                      expand_context_window_turns: Number(e.target.value) || 1,
                    }))
                  }
                  className="w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-sm text-on-surface/95 focus:outline-none focus:border-primary/60"
                />
                <span className="text-[11px] text-on-surface/55 leading-snug">
                  How many latest transcript turns are sent when expanding a clicked suggestion.
                </span>
              </label>
              <label className="flex flex-col gap-1 sm:col-span-2">
                <span className="text-xs text-on-surface/70">Fact-check threshold (0-1)</span>
                <input
                  type="number"
                  min={0}
                  max={1}
                  step={0.01}
                  value={settingsDraft.fact_check_score_threshold}
                  onChange={(e) =>
                    setSettingsDraft((prev) => ({
                      ...prev,
                      fact_check_score_threshold: Number(e.target.value) || 0,
                    }))
                  }
                  className="w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-sm text-on-surface/95 focus:outline-none focus:border-primary/60"
                />
                <span className="text-[11px] text-on-surface/55 leading-snug">
                  Controls when verify/fact-check runs after ranking. Lower = more verification (slower, stricter).
                  Higher = less verification (faster).
                </span>
              </label>
            </div>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-on-surface/70">Live suggestions prompt override</span>
              <textarea
                value={settingsDraft.live_prompt_template}
                onChange={(e) => setSettingsDraft((prev) => ({ ...prev, live_prompt_template: e.target.value }))}
                className="min-h-24 w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-xs text-on-surface/95 focus:outline-none focus:border-primary/60 font-mono"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-on-surface/70">Expand prompt override</span>
              <textarea
                value={settingsDraft.expand_prompt_template}
                onChange={(e) => setSettingsDraft((prev) => ({ ...prev, expand_prompt_template: e.target.value }))}
                className="min-h-20 w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-xs text-on-surface/95 focus:outline-none focus:border-primary/60 font-mono"
              />
            </label>
            <label className="flex flex-col gap-1">
              <span className="text-xs text-on-surface/70">Chat prompt override</span>
              <textarea
                value={settingsDraft.chat_prompt_template}
                onChange={(e) => setSettingsDraft((prev) => ({ ...prev, chat_prompt_template: e.target.value }))}
                className="min-h-20 w-full bg-white/[0.08] border border-white/20 rounded-lg px-3 py-2 text-xs text-on-surface/95 focus:outline-none focus:border-primary/60 font-mono"
              />
            </label>
            {settingsError && <p className="text-sm text-rose-300/90">{settingsError}</p>}
            {settingsSuccess && <p className="text-sm text-emerald-300/90">{settingsSuccess}</p>}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setSettingsModalOpen(false)}
                className="ui-btn ui-btn-ghost text-sm rounded-lg px-3.5 py-2"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void handleSaveSettings()}
                className="ui-btn text-sm rounded-lg px-3.5 py-2"
                disabled={isSavingSettings}
              >
                {isSavingSettings ? 'Saving…' : 'Save settings'}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  )
}

export default App
