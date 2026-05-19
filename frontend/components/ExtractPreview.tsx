'use client'

import { useEffect, useRef, useState } from 'react'
import {
  getExtractionPreview,
  getExtractionStatus,
  getJobCropUrl,
  getJobDownloadUrl,
  type Crop,
  type JobStatus,
} from '@/lib/api'

const POLL_INTERVAL_MS = 1000

interface ExtractPreviewProps {
  jobId: string
  onReset: () => void
}

export default function ExtractPreview({ jobId, onReset }: ExtractPreviewProps) {
  const [status, setStatus] = useState<JobStatus>('queued')
  const [progress, setProgress] = useState(0)
  const [total, setTotal] = useState(0)
  const [crops, setCrops] = useState<Crop[]>([])
  const [error, setError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return
    let cancelled = false

    const tick = async () => {
      try {
        const [st, pv] = await Promise.all([
          getExtractionStatus(jobId),
          getExtractionPreview(jobId),
        ])
        if (cancelled) return

        setStatus(st.status)
        setProgress(st.progress)
        setTotal(st.total)
        setCrops(pv.crops)

        if (st.status === 'error') {
          setError(st.error || 'Extraction failed')
          if (pollRef.current) clearInterval(pollRef.current)
        }
        if (st.status === 'done') {
          if (pollRef.current) clearInterval(pollRef.current)
        }
      } catch (err) {
        if (!cancelled) console.error('Polling error', err)
      }
    }

    tick()
    pollRef.current = setInterval(tick, POLL_INTERVAL_MS)
    return () => {
      cancelled = true
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [jobId])

  const pct = total > 0 ? Math.round((progress / total) * 100) : 0
  const isDone = status === 'done'
  const isError = status === 'error'

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.24em] text-blue-600 font-semibold">Step 2</p>
            <h2 className="mt-2 text-2xl font-semibold text-slate-900">
              {isDone ? 'Extraction complete' : isError ? 'Extraction failed' : 'Generating crops'}
            </h2>
            <p className="mt-3 text-sm text-slate-500 max-w-2xl">
              {isError
                ? error
                : total > 0
                  ? `Processed ${progress} of ${total} frames (${pct}%).`
                  : 'Filtering CSV and decoding video. A live preview will appear here shortly.'}
            </p>
          </div>

          <div className="flex flex-wrap gap-3">
            {isDone && crops.length > 0 && (
              <button
                type="button"
                onClick={() => window.open(getJobDownloadUrl(jobId), '_self')}
                className="inline-flex h-12 items-center justify-center rounded-3xl bg-blue-600 px-6 text-sm font-semibold text-white shadow hover:bg-blue-700"
              >
                Download .zip ({crops.length} crops)
              </button>
            )}
            <button
              onClick={onReset}
              className="inline-flex h-12 items-center justify-center rounded-3xl border border-slate-300 bg-white px-6 text-sm font-semibold text-slate-700 hover:bg-slate-50"
            >
              {isDone ? 'New extraction' : 'Cancel'}
            </button>
          </div>
        </div>

        {!isError && (
          <div className="mt-6 rounded-full bg-slate-100 h-3 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${isDone ? 'bg-emerald-500' : 'bg-blue-600'}`}
              style={{ width: `${total > 0 ? pct : status === 'queued' ? 8 : 22}%` }}
            />
          </div>
        )}
      </div>

      {error && (
        <div className="rounded-3xl border border-red-200 bg-red-50 p-5 text-sm text-red-700 shadow-sm">
          {error}
        </div>
      )}

      {crops.length === 0 ? (
        <div className="rounded-3xl border border-dashed border-slate-200 bg-slate-50 p-12 text-center text-slate-500">
          {isError ? 'No crops are available.' : 'Crops will appear here as they are extracted.'}
        </div>
      ) : (
        <section className="space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-sm text-slate-500">Preview</p>
              <h3 className="text-xl font-semibold text-slate-900">Generated crops</h3>
            </div>
            <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold text-slate-600">
              {crops.length} items
            </span>
          </div>

          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5">
            {crops.map((crop) => (
              <CropCard key={crop.uid} crop={crop} />
            ))}
          </div>
        </section>
      )}
    </div>
  )
}

interface CropCardProps {
  crop: Crop
}

function CropCard({ crop }: CropCardProps) {
  return (
    <div className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-sm">
      <div className="aspect-video bg-slate-100 relative overflow-hidden">
        <img
          src={getJobCropUrl(crop.image_url)}
          alt={`uid ${crop.uid}`}
          className="h-full w-full object-cover"
          loading="lazy"
        />
        <div className="absolute left-2 top-2 rounded-full bg-slate-900/80 px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.2em] text-white">
          {crop.class_name || 'obj'}
        </div>
      </div>
      <div className="space-y-2 p-3 text-sm text-slate-600">
        <p className="font-medium truncate">uid {crop.uid}</p>
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>track {crop.track_id}</span>
          <span>{(crop.confidence * 100).toFixed(0)}%</span>
        </div>
      </div>
    </div>
  )
}