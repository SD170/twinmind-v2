import type { BucketType } from '../../types/api'

export function formatTranscriptTime(ms: number) {
  const seconds = Math.max(0, Math.floor(ms / 1000))
  const mins = Math.floor(seconds / 60)
  const rem = seconds % 60
  return `${mins.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`
}

export function relTime(createdAt: number, now = Date.now()): string {
  const s = Math.max(0, Math.floor((now - createdAt) / 1000))
  if (s < 15) return 'Just now'
  if (s < 60) return `${s}s ago`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

/** Split long card text into a headline (first sentence) + body, matching the Stitch two-line cards. */
export function cardHeadline(text: string): { title: string; body: string } {
  const trimmed = text.trim()
  const m = /[.!?](?:\s|$)/.exec(trimmed)
  if (m && m.index !== undefined && m.index > 0 && m.index < 100) {
    return {
      title: trimmed.slice(0, m.index + 1).trim(),
      body: trimmed.slice(m.index + 1).trim(),
    }
  }
  if (trimmed.length <= 72) {
    return { title: trimmed, body: '' }
  }
  const cut = trimmed.lastIndexOf(' ', 70)
  const t = (cut > 20 ? trimmed.slice(0, cut) : trimmed.slice(0, 70)) + '…'
  return { title: t, body: trimmed }
}

const BUCKET_UI: Record<
  BucketType,
  { label: string; tagClass: string; borderClass: string; icon: string }
> = {
  answer: {
    label: 'Answer',
    tagClass: 'bg-primary/20 text-primary border border-primary/25',
    borderClass: 'border border-primary/20 hover:border-primary/55',
    icon: 'open_in_new',
  },
  fact_check: {
    label: 'Fact-Check',
    tagClass: 'bg-orange-500/20 text-orange-300 border border-orange-500/30',
    borderClass: 'border border-orange-500/30 border-l-[3px] border-l-orange-500 hover:border-orange-400/50',
    icon: 'bolt',
  },
  question: {
    label: 'Question',
    tagClass: 'bg-purple-500/20 text-purple-200 border border-purple-500/30',
    borderClass: 'border border-purple-500/30 hover:border-purple-400/50',
    icon: 'help',
  },
  talking_point: {
    label: 'Talking Point',
    tagClass: 'bg-sky-500/20 text-sky-300 border border-sky-500/35',
    borderClass: 'border border-sky-500/35 hover:border-sky-400/55',
    icon: 'lightbulb',
  },
}

export function bucketUi(bucket: BucketType) {
  return BUCKET_UI[bucket] ?? BUCKET_UI.answer
}

const BUCKET_LABEL: Record<BucketType, string> = {
  answer: 'Answer',
  fact_check: 'Fact-Check',
  talking_point: 'Talking Point',
  question: 'Question',
}

/** Human label for an omitted bucket or raw bucket string. */
export function labelForBucketKey(s: string): string {
  return (BUCKET_LABEL as Record<string, string>)[s] ?? s.replace(/_/g, ' ')
}
