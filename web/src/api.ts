export type CheckName = 'missing_links' | 'negative_float' | 'high_float'

export interface Finding {
  check: CheckName
  task_code: string
  task_name: string
  task_type: string
  detail: string
  value: number | null
  line: number
}

export interface BrokenRow {
  line: number
  table: string | null
  reason: string
  raw: string
}

export interface ExternalLink {
  task_id: string
  pred_task_id: string
  pred_proj_id: string
}

export interface CheckResponse {
  file: string
  activity_count: number
  unscheduled_count: number
  high_float_threshold_days: number
  counts: Record<CheckName, number>
  findings: Record<CheckName, Finding[]>
  broken_rows: BrokenRow[]
  external_links: ExternalLink[]
  external_link_count: number
  chart_png_base64: string
  xer: {
    version: string
    export_date: string
    encoding: string
    line_count: number
    relationship_count: number
    projects: { id: string; short_name: string; name: string }[]
  }
}

export interface Sample {
  name: string
  bytes: number
  kind: 'public' | 'fixture'
}

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T
  let detail = `${res.status} ${res.statusText}`
  try {
    const body = await res.json()
    if (typeof body.detail === 'string') detail = body.detail
  } catch {
    /* non-JSON error body */
  }
  throw new Error(detail)
}

export const listSamples = () => fetch('/api/samples').then((r) => parse<Sample[]>(r))

export const checkSample = (name: string, highFloatDays: number) =>
  fetch(`/api/samples/${encodeURIComponent(name)}?high_float_days=${highFloatDays}`).then((r) =>
    parse<CheckResponse>(r),
  )

export const checkUpload = (file: File, highFloatDays: number) => {
  const body = new FormData()
  body.append('file', file)
  return fetch(`/api/check?high_float_days=${highFloatDays}`, { method: 'POST', body }).then((r) =>
    parse<CheckResponse>(r),
  )
}

export interface TableSummary {
  name: string
  rows: number
  columns: number
}

export interface TablesResponse {
  file: string
  xer: { version: string; export_date: string; encoding: string; line_count: number }
  header: string[]
  broken_row_count: number
  tables: TableSummary[]
}

export interface TablePage {
  file: string
  table: string
  fields: string[]
  total: number
  offset: number
  rows: string[][]
  lines: number[]
}

export const listTables = (name: string) =>
  fetch(`/api/samples/${encodeURIComponent(name)}/tables`).then((r) => parse<TablesResponse>(r))

export const fetchTablePage = (name: string, table: string, offset: number, limit = 50) =>
  fetch(`/api/samples/${encodeURIComponent(name)}/tables/${encodeURIComponent(table)}?offset=${offset}&limit=${limit}`).then(
    (r) => parse<TablePage>(r),
  )
