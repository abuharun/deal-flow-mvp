/**
 * The pitch deck: choose a PDF, upload it, replace it, remove it, read it back.
 *
 * The upload button appears only once a file has actually been chosen — a
 * control that can only fail is worse than no control. Every refusal the
 * backend can return (wrong MIME, too large, encrypted, page count) is a
 * canonical code, so this panel shows the API's own reason rather than a
 * guess of its own; the browser-side `accept` filter is a convenience, never
 * the validation.
 */

import { useRef, useState } from 'react'
import type { DeckResponse } from '../../api/types'
import { useLocale } from '../../i18n'
import { formatBytes, formatDate } from '../../lib/format'
import { ErrorPanel } from '../states'

export default function DeckPanel({
  deck,
  locked,
  uploading,
  uploadError,
  onUpload,
  deleting,
  deleteError,
  onDelete,
  onDownload,
}: {
  deck: DeckResponse | null
  locked: boolean
  uploading: boolean
  uploadError: unknown
  onUpload: (file: File) => void
  deleting: boolean
  deleteError: unknown
  onDelete: () => void
  onDownload: () => void
}) {
  const { locale, t } = useLocale()
  const [chosen, setChosen] = useState<File | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const metadata = deck && (
    <>
      <p>
        <strong>{deck.filename}</strong>
      </p>
      <p className="faint">
        {t.work.deckPages(deck.page_count)} · {formatBytes(deck.size_bytes, locale)} · {t.work.deckUploadedAt}:{' '}
        {formatDate(deck.uploaded_at, locale)}
      </p>
    </>
  )

  if (locked) {
    return <div className="step-body">{metadata ?? <p className="muted">{t.work.deckNone}</p>}</div>
  }

  return (
    <div className="step-body">
      {metadata ?? <p className="muted">{t.work.deckNone}</p>}
      <p className="faint">{t.work.deckLede}</p>

      <div className="field">
        <label htmlFor="deck-file">{t.work.deckChoose}</label>
        <input
          id="deck-file"
          ref={inputRef}
          className="input"
          type="file"
          accept="application/pdf,.pdf"
          onChange={(event) => setChosen(event.target.files?.[0] ?? null)}
        />
      </div>

      {uploadError !== null && uploadError !== undefined && <ErrorPanel error={uploadError} />}
      {deleteError !== null && deleteError !== undefined && <ErrorPanel error={deleteError} />}

      <div className="list-toolbar">
        {chosen && (
          <button
            type="button"
            className="btn btn-primary btn-sm"
            disabled={uploading}
            onClick={() => onUpload(chosen)}
          >
            {uploading ? t.work.deckUploading : deck ? t.work.deckReplace : t.work.deckUpload}
          </button>
        )}
        {deck && (
          <>
            <button type="button" className="btn btn-quiet btn-sm" onClick={onDownload}>
              {t.work.deckDownload}
            </button>
            <button
              type="button"
              className="btn btn-quiet btn-sm"
              disabled={deleting}
              onClick={() => {
                // Clear the picker too: a stale selection next to "no deck
                // uploaded" invites an accidental re-upload of the old file.
                setChosen(null)
                if (inputRef.current) inputRef.current.value = ''
                onDelete()
              }}
            >
              {t.work.deckDelete}
            </button>
          </>
        )}
      </div>
    </div>
  )
}
