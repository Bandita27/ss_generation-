'use client'

import { useState } from 'react'
import ExtractForm from '@/components/ExtractForm'
import ExtractPreview from '@/components/ExtractPreview'

type View = 'extract' | 'preview'

const STEP_LABELS: Record<View, string> = {
  extract: 'Upload',
  preview: 'Preview',
}

export default function Page() {
  const [view, setView] = useState<View>('extract')
  const [extractJobId, setExtractJobId] = useState<string | null>(null)

  const handleExtractStarted = (jobId: string) => {
    setExtractJobId(jobId)
    setView('preview')
  }

  const handleReset = () => {
    setExtractJobId(null)
    setView('extract')
  }

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="bg-white border-b border-slate-200 px-6 py-5 sticky top-0 z-20 shadow-sm">
        <div className="mx-auto max-w-7xl flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm uppercase tracking-[0.3em] text-blue-700 font-semibold">Crop extraction</p>
            <h1 className="mt-2 text-2xl font-semibold text-slate-900">Video → Crop Generator</h1>
            <p className="mt-2 max-w-2xl text-sm text-slate-500">
              Upload a tracked video + CSV, generate annotated crops, and download the result.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            {(Object.entries(STEP_LABELS) as [View, string][]).map(([key, label]) => (
              <span
                key={key}
                className={
                  'rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.15em] ' +
                  (view === key
                    ? 'bg-blue-600 text-white shadow-sm'
                    : 'bg-slate-100 text-slate-600')
                }
              >
                {label}
              </span>
            ))}
          </div>
        </div>
      </header>

      <main className="p-6">
        {view === 'extract' && <ExtractForm onStarted={handleExtractStarted} />}
        {view === 'preview' && extractJobId && (
          <ExtractPreview jobId={extractJobId} onReset={handleReset} />
        )}
      </main>
    </div>
  )
}