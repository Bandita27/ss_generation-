'use client'

import { useState } from 'react'
import type { AxiosProgressEvent } from 'axios'
import { startExtraction } from '@/lib/api'

interface ExtractFormProps {
  onStarted: (jobId: string) => void
}

interface ExtractionConfig {
  conf_threshold: number
  sample_every: number
  track_col: string
  frame_col: string
  conf_col: string
  bbox_format: string
  bbox_x: string
  bbox_y: string
  bbox_w: string
  bbox_h: string
}

const DEFAULT_CONFIG: ExtractionConfig = {
  conf_threshold: 0.5,
  sample_every: 10,
  track_col: 'track_id',
  frame_col: 'frame',
  conf_col: 'confidence',
  bbox_format: 'xywh',
  bbox_x: 'x',
  bbox_y: 'y',
  bbox_w: 'w',
  bbox_h: 'h',
}

export default function ExtractForm({ onStarted }: ExtractFormProps) {
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [csvFile, setCsvFile] = useState<File | null>(null)
  const [config, setConfig] = useState<ExtractionConfig>(DEFAULT_CONFIG)
  const [submitting, setSubmitting] = useState(false)
  const [uploadPct, setUploadPct] = useState(0)
  const [error, setError] = useState<string | null>(null)

  const handleStart = async () => {
    if (!videoFile || !csvFile) return
    setSubmitting(true)
    setError(null)
    setUploadPct(0)
    try {
      const jobId = await startExtraction(
        { video: videoFile, csv: csvFile, ...config },
        (e: AxiosProgressEvent) => {
          if (e.total) setUploadPct(Math.round((e.loaded / e.total) * 100))
        },
      )
      onStarted(jobId)
    } catch (err) {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      const fallback = err instanceof Error ? err.message : 'Failed to start job'
      setError(detail || fallback)
      setSubmitting(false)
    }
  }

  const canStart = Boolean(videoFile && csvFile && !submitting)

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <section className="rounded-3xl bg-white p-6 shadow-sm border border-slate-200">
        <div className="flex flex-col gap-2">
          <p className="text-sm uppercase tracking-[0.24em] text-blue-600 font-semibold">Step 1</p>
          <h2 className="text-3xl font-semibold text-slate-900">Create a new extraction job</h2>
          <p className="max-w-2xl text-sm text-slate-500">
            Upload your source video and matching tracking CSV. Then fine-tune confidence and sampling before running extraction.
          </p>
        </div>

        <div className="mt-8 grid gap-4 sm:grid-cols-2">
          <FileDropzone label="Video file" accept="video/*" file={videoFile} onChange={setVideoFile} />
          <FileDropzone label="Tracking CSV" accept=".csv,text/csv" file={csvFile} onChange={setCsvFile} />
        </div>

        <div className="mt-8 rounded-3xl border border-slate-200 bg-slate-50 p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-slate-900">Extraction parameters</p>
              <p className="text-sm text-slate-500">Control confidence filtering and sampling before preview generation.</p>
            </div>
            <span className="inline-flex items-center rounded-full bg-blue-100 px-3 py-1 text-xs font-semibold text-blue-700">
              Auto-detect columns from CSV
            </span>
          </div>

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <NumField
              label="Confidence threshold"
              hint="Drop detections below this"
              step="0.05"
              min="0"
              max="1"
              value={config.conf_threshold}
              onChange={(v) => setConfig({ ...config, conf_threshold: parseFloat(v) || 0 })}
            />
            <NumField
              label="Sample every (per track)"
              hint="Keep 1st, 11th, 21st…"
              step="1"
              min="1"
              value={config.sample_every}
              onChange={(v) => setConfig({ ...config, sample_every: parseInt(v, 10) || 1 })}
            />
          </div>
        </div>

        {error && (
          <div className="mt-6 rounded-3xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
            {error}
          </div>
        )}

        <button
          onClick={handleStart}
          disabled={!canStart}
          className="mt-6 inline-flex h-14 w-full items-center justify-center rounded-3xl bg-blue-600 px-6 text-base font-semibold text-white shadow-lg shadow-blue-500/10 transition hover:bg-blue-700 disabled:bg-slate-300 disabled:text-slate-500"
        >
          {submitting
            ? uploadPct > 0 && uploadPct < 100
              ? `Uploading ${uploadPct}%…`
              : 'Starting job…'
            : 'Start extraction'}
        </button>
      </section>
    </div>
  )
}

interface FileDropzoneProps {
  label: string
  accept: string
  file: File | null
  onChange: (file: File | null) => void
}

function FileDropzone({ label, accept, file, onChange }: FileDropzoneProps) {
  return (
    <label className="block rounded-3xl border border-slate-200 bg-slate-50 p-5 transition hover:border-blue-300 hover:bg-white cursor-pointer">
      <p className="text-sm font-semibold text-slate-700 mb-3">{label}</p>
      <input
        type="file"
        accept={accept}
        className="hidden"
        onChange={(e) => onChange(e.target.files?.[0] || null)}
      />
      <div className="h-36 flex flex-col items-center justify-center gap-2 rounded-3xl border-2 border-dashed border-slate-300 bg-white/80 p-4 text-center transition">
        {file ? (
          <>
            <p className="text-sm font-semibold text-slate-900 truncate">{file.name}</p>
            <p className="text-xs text-slate-500">{(file.size / 1_000_000).toFixed(1)} MB</p>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-500">Click to choose a file</p>
            <p className="text-xs text-slate-400">Supported formats: MP4, MOV, CSV</p>
          </>
        )}
      </div>
    </label>
  )
}

interface NumFieldProps {
  label: string
  hint?: string
  value: number
  onChange: (value: string) => void
  step?: string
  min?: string
  max?: string
}

function NumField({ label, hint, value, onChange, ...props }: NumFieldProps) {
  return (
    <div className="space-y-2">
      <label className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{label}</label>
      <input
        type="number"
        value={value}
        className="w-full rounded-2xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 shadow-sm"
        onChange={(e) => onChange(e.target.value)}
        {...props}
      />
      {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
    </div>
  )
}