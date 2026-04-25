import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App'

describe('App', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ status: 'ok' }),
      })
    )
  })

  it('renders first two columns and controls', async () => {
    render(<App />)

    expect(await screen.findByText('TwinMind - Live Suggestions')).toBeInTheDocument()
    expect(screen.getByText('1. Mic & Transcript')).toBeInTheDocument()
    expect(screen.getByText('2. Live Suggestions')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start mic/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reload suggestions/i })).toBeInTheDocument()
  })
})
