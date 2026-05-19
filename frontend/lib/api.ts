import axios, { type AxiosProgressEvent } from 'axios'

const BASE_URL = process.env.NEXT_PUBLIC_BASE_URL ?? 'http://ss_backend:8001'

const api = axios.create({ baseURL: BASE_URL })

export type JobStatus = 'queued' | 'processing' | 'done' | 'error'

export interface ExtractionStartResponse {
  job_id: string
}

export interface ExtractionStatus {
  status: JobStatus
  progress: number
  total: number
  error: string | null
}

export interface Crop {
  uid: number
  track_id: number
  frame: number
  confidence: number
  class_name: string
  image_url: string
}

export interface ExtractionPreview {
  job_id: string
  status: JobStatus
  progress: number
  total: number
  crops: Crop[]
  source_video_name: string
  source_csv_name: string
}

export interface ExtractionPayload {
  video: File
  csv: File
  conf_threshold?: number
  sample_every?: number
  track_col?: string
  frame_col?: string
  conf_col?: string
  bbox_format?: string
  bbox_x?: string
  bbox_y?: string
  bbox_w?: string
  bbox_h?: string
}

export async function fetchCsvHeaders(csvFile: File): Promise<string[]> {
  const fd = new FormData()
  fd.append('csv', csvFile)
  const { data } = await api.post<{ headers: string[] }>('/extract/headers', fd)
  return data.headers
}

export async function startExtraction(
  payload: ExtractionPayload,
  onUploadProgress?: (e: AxiosProgressEvent) => void,
): Promise<string> {
  const fd = new FormData()
  fd.append('video', payload.video)
  fd.append('csv', payload.csv)

  const fields: Record<string, string | number> = {
    conf_threshold: payload.conf_threshold ?? 0.5,
    sample_every: payload.sample_every ?? 10,
    track_col: payload.track_col || 'track_id',
    frame_col: payload.frame_col || 'frame',
    conf_col: payload.conf_col || 'confidence',
    bbox_format: payload.bbox_format || 'xywh',
    bbox_x: payload.bbox_x || 'x',
    bbox_y: payload.bbox_y || 'y',
    bbox_w: payload.bbox_w || 'w',
    bbox_h: payload.bbox_h || 'h',
  }
  for (const [k, v] of Object.entries(fields)) {
    fd.append(k, String(v))
  }

  const { data } = await api.post<ExtractionStartResponse>('/extract', fd, { onUploadProgress })
  return data.job_id
}

export async function getExtractionStatus(jobId: string): Promise<ExtractionStatus> {
  const { data } = await api.get<ExtractionStatus>(`/extract/${jobId}/status`)
  return data
}

export async function getExtractionPreview(jobId: string): Promise<ExtractionPreview> {
  const { data } = await api.get<ExtractionPreview>(`/extract/${jobId}/preview`)
  return data
}

export function getJobCropUrl(relativeUrl: string): string {
  return `${BASE_URL}${relativeUrl}`
}

export function getJobDownloadUrl(jobId: string): string {
  return `${BASE_URL}/extract/${jobId}/download`
}