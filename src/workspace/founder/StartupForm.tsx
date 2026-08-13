/**
 * The startup metadata form, shared by "create" and "edit".
 *
 * One form for both because the backend takes the same five fields either
 * way (backend/app/schemas/startup.py). The difference is only in what gets
 * sent: creating posts all five, editing PATCHes exactly the fields the
 * founder actually changed — the patch schema treats absent and null
 * differently, so sending an untouched field back would be a lie about
 * intent, not a harmless no-op.
 */

import { useState, type FormEvent } from 'react'
import type { StartupCreateRequest, StartupPatchRequest, StartupResponse } from '../../api/types'
import { useLocale } from '../../i18n'
import { ErrorPanel } from '../states'

export type MetadataField = 'name' | 'one_liner' | 'sector' | 'funding_stage' | 'city'

const FIELDS: MetadataField[] = ['name', 'one_liner', 'sector', 'funding_stage', 'city']

export type MetadataDraft = Record<MetadataField, string>

export function draftFrom(startup: StartupResponse): MetadataDraft {
  return {
    name: startup.name,
    one_liner: startup.one_liner,
    sector: startup.sector,
    funding_stage: startup.funding_stage,
    city: startup.city,
  }
}

const EMPTY_DRAFT: MetadataDraft = { name: '', one_liner: '', sector: '', funding_stage: '', city: '' }

/** Only the fields that actually differ from what the API last returned. */
export function changedFields(before: MetadataDraft, after: MetadataDraft): StartupPatchRequest {
  const changes: StartupPatchRequest = {}
  for (const field of FIELDS) {
    if (after[field].trim() !== before[field]) changes[field] = after[field].trim()
  }
  return changes
}

export function StartupForm({
  initial,
  busy,
  error,
  submitLabel,
  onSubmit,
  onCancel,
  idPrefix,
}: {
  /** Absent when creating: the form starts blank. */
  initial?: StartupResponse
  busy: boolean
  error: unknown
  submitLabel: string
  /** Receives the full draft; the caller decides create vs. diffed patch. */
  onSubmit: (draft: MetadataDraft) => void
  onCancel: () => void
  /** Keeps label/input ids unique when two forms could coexist. */
  idPrefix: string
}) {
  const { t } = useLocale()
  const [draft, setDraft] = useState<MetadataDraft>(initial ? draftFrom(initial) : EMPTY_DRAFT)

  const labels: Record<MetadataField, string> = {
    name: t.work.nameLabel,
    one_liner: t.work.oneLinerLabel,
    sector: t.work.sectorLabel,
    funding_stage: t.work.fundingStageLabel,
    city: t.work.cityLabel,
  }

  const submit = (event: FormEvent) => {
    event.preventDefault()
    // The API rejects a blank name; refusing here keeps the founder's typing
    // rather than round-tripping to a 422 that says the same thing.
    if (!draft.name.trim()) return
    onSubmit(draft)
  }

  return (
    <form className="card startup-form" onSubmit={submit} noValidate>
      {FIELDS.map((field) => (
        <div className="field" key={field}>
          <label htmlFor={`${idPrefix}-${field}`}>{labels[field]}</label>
          <input
            id={`${idPrefix}-${field}`}
            className="input"
            type="text"
            value={draft[field]}
            onChange={(event) => setDraft({ ...draft, [field]: event.target.value })}
          />
        </div>
      ))}
      {error !== null && error !== undefined && <ErrorPanel error={error} />}
      <div className="list-toolbar">
        <button type="submit" className="btn btn-primary btn-sm" disabled={busy}>
          {busy ? t.work.saving : submitLabel}
        </button>
        <button type="button" className="btn btn-quiet btn-sm" onClick={onCancel} disabled={busy}>
          {t.work.cancel}
        </button>
      </div>
    </form>
  )
}

/** The create payload: every field, trimmed, exactly as the POST schema wants. */
export function createPayload(draft: MetadataDraft): StartupCreateRequest {
  return {
    name: draft.name.trim(),
    one_liner: draft.one_liner.trim(),
    sector: draft.sector.trim(),
    funding_stage: draft.funding_stage.trim(),
    city: draft.city.trim(),
  }
}
