import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { AppRoutes } from '../App'
import { StoreProvider, initialState, reducer } from '../lib/store'
import { ToastProvider } from '../components/toast'
import { opaqueId } from '../lib/simulate'
import { LocaleProvider } from '../i18n'
import type { AppState } from '../lib/types'

// jsdom ships no IndexedDB, so the focused blob-storage seam is mocked with an
// in-memory map; production code paths (validation, replace, error handling)
// stay fully real.
const seam = vi.hoisted(() => {
  const blobs = new Map<string, Blob>()
  return {
    blobs,
    putBlob: vi.fn(async (key: string, blob: Blob) => {
      blobs.set(key, blob)
    }),
    getBlob: vi.fn(async (key: string) => blobs.get(key) ?? null),
    deleteBlob: vi.fn(async (key: string) => {
      blobs.delete(key)
    }),
    clearBlobs: vi.fn(async () => {
      blobs.clear()
    }),
  }
})
vi.mock('../lib/blobStore', () => seam)

function renderAt(path: string) {
  return render(
    <LocaleProvider>
      <StoreProvider>
        <ToastProvider>
          <MemoryRouter initialEntries={[path]}>
            <AppRoutes />
          </MemoryRouter>
        </ToastProvider>
      </StoreProvider>
    </LocaleProvider>,
  )
}

function seedSession(role: 'founder' | 'vc') {
  localStorage.setItem('oqim:v2', JSON.stringify(reducer(initialState(), { type: 'login', role })))
}

const DECK_LABEL_UZ = 'Pitch-dek (PDF, maks. 10 MB)'
const REVENUE_LABEL_UZ = 'Daromad isboti (PDF, maks. 10 MB)'

function pdfFile(name = 'my-real-deck.pdf', content = '%PDF-1.4 demo'): File {
  return new File([content], name, { type: 'application/pdf' })
}

beforeEach(() => {
  vi.clearAllMocks()
  seam.blobs.clear()
  localStorage.clear()
  URL.createObjectURL = vi.fn(() => 'blob:mock-url')
  URL.revokeObjectURL = vi.fn()
})

describe('founder PDF attachments', () => {
  it('offers a real PDF-only file input and lists the selected deck by name and size', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    const input = screen.getByLabelText(DECK_LABEL_UZ) as HTMLInputElement
    expect(input).toHaveAttribute('type', 'file')
    expect(input).toHaveAttribute('accept', 'application/pdf,.pdf')

    await user.upload(input, pdfFile())
    expect(await screen.findByText(/my-real-deck\.pdf/)).toBeInTheDocument()
    // 13-byte demo PDF → human-readable size next to the real filename.
    expect(screen.getByText(/13 B/)).toBeInTheDocument()
    expect(seam.putBlob).toHaveBeenCalledWith('attachment:deck', expect.any(File))

    // Metadata (not bytes) flows through the existing localStorage draft.
    const persisted = JSON.parse(localStorage.getItem('oqim:v2')!) as AppState
    expect(persisted.draft.attachments).toEqual([
      expect.objectContaining({
        kind: 'deck',
        fileName: 'my-real-deck.pdf',
        storageKey: 'attachment:deck',
        mimeType: 'application/pdf',
        size: 13,
      }),
    ])
  })

  it('accepts a revenue-proof PDF through its own PDF-only input', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    const input = screen.getByLabelText(REVENUE_LABEL_UZ) as HTMLInputElement
    expect(input).toHaveAttribute('accept', 'application/pdf,.pdf')
    await user.upload(input, pdfFile('bank-proof.pdf'))
    expect(await screen.findByText(/bank-proof\.pdf/)).toBeInTheDocument()
    expect(seam.putBlob).toHaveBeenCalledWith('attachment:revenue', expect.any(File))
  })

  it('rejects a non-PDF file with a localized error and stores nothing', async () => {
    const user = userEvent.setup({ applyAccept: false })
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    const sheet = new File(['a,b'], 'statement.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    await user.upload(screen.getByLabelText(DECK_LABEL_UZ), sheet)

    expect(await screen.findByRole('alert')).toHaveTextContent('Faqat PDF fayl qabul qilinadi.')
    expect(screen.queryByText(/statement\.xlsx/)).not.toBeInTheDocument()
    expect(seam.putBlob).not.toHaveBeenCalled()
  })

  it('rejects a PDF over 10 MiB with a localized error', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    const big = pdfFile('huge.pdf')
    Object.defineProperty(big, 'size', { value: 10 * 1024 * 1024 + 1 })
    await user.upload(screen.getByLabelText(DECK_LABEL_UZ), big)

    expect(await screen.findByRole('alert')).toHaveTextContent('Fayl hajmi 10 MB dan oshmasligi kerak.')
    expect(screen.queryByText(/huge\.pdf/)).not.toBeInTheDocument()
    expect(seam.putBlob).not.toHaveBeenCalled()
  })

  it('surfaces a storage failure instead of pretending the file was saved', async () => {
    const user = userEvent.setup()
    seam.putBlob.mockRejectedValueOnce(new Error('quota exceeded'))
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    await user.upload(screen.getByLabelText(DECK_LABEL_UZ), pdfFile('fails.pdf'))

    expect(await screen.findByRole('alert')).toHaveTextContent(/saqlab bo'lmadi/)
    expect(screen.queryByText(/fails\.pdf/)).not.toBeInTheDocument()
    const persisted = JSON.parse(localStorage.getItem('oqim:v2')!) as AppState
    expect(persisted.draft.attachments).toEqual([])
  })

  it('replaces the previous deck when a new PDF is selected', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    await user.upload(screen.getByLabelText(DECK_LABEL_UZ), pdfFile('first.pdf'))
    expect(await screen.findByText(/first\.pdf/)).toBeInTheDocument()
    await user.upload(screen.getByLabelText(DECK_LABEL_UZ), pdfFile('second.pdf'))

    expect(await screen.findByText(/second\.pdf/)).toBeInTheDocument()
    expect(screen.queryByText(/first\.pdf/)).not.toBeInTheDocument()
    // Both writes reuse the stable per-kind key, so no orphan blob is left.
    expect(seam.putBlob).toHaveBeenNthCalledWith(1, 'attachment:deck', expect.any(File))
    expect(seam.putBlob).toHaveBeenNthCalledWith(2, 'attachment:deck', expect.any(File))
  })

  it('deletes the stored bytes when an uploaded attachment is removed', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    await user.upload(screen.getByLabelText(DECK_LABEL_UZ), pdfFile())
    expect(await screen.findByText(/my-real-deck\.pdf/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Pitch-dek faylini olib tashlash' }))
    expect(screen.queryByText(/my-real-deck\.pdf/)).not.toBeInTheDocument()
    expect(seam.deleteBlob).toHaveBeenCalledWith('attachment:deck')
  })

  it('adds a data room URL through a real URL input', async () => {
    const user = userEvent.setup()
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    await user.type(screen.getByLabelText('Data room havolasi (URL)'), 'drive.google.com/my-room')
    await user.click(screen.getByRole('button', { name: "Havolani qo'shish" }))

    expect(await screen.findByText(/https:\/\/drive\.google\.com\/my-room/)).toBeInTheDocument()
    // Links need no bytes: the blob store is never touched.
    expect(seam.putBlob).not.toHaveBeenCalled()
  })

  it('shows Russian validation errors under the Russian interface', async () => {
    const user = userEvent.setup({ applyAccept: false })
    localStorage.setItem('oqim:locale', 'ru')
    seedSession('founder')
    renderAt('/apply/submit?step=ask')

    const input = screen.getByLabelText('Питч-дек (PDF, макс. 10 МБ)')
    const sheet = new File(['a,b'], 'statement.xlsx', { type: 'text/csv' })
    await user.upload(input, sheet)
    expect(await screen.findByRole('alert')).toHaveTextContent('Принимается только файл PDF.')
  })
})

describe('VC attachment access', () => {
  function seedVcWithUploads(): string {
    const base = reducer(initialState(), { type: 'login', role: 'vc' })
    const id = opaqueId('xarid')
    const state: AppState = {
      ...base,
      startups: base.startups.map((s) =>
        s.id === id
          ? {
              ...s,
              attachments: [
                ...s.attachments,
                {
                  label: 'Pitch-dek',
                  kind: 'deck' as const,
                  fileName: 'uploaded-real-deck.pdf',
                  storageKey: 'attachment:deck',
                  mimeType: 'application/pdf',
                  size: 2456789,
                },
                {
                  label: 'Data room havolasi',
                  kind: 'dataroom' as const,
                  fileName: 'https://drive.example.com/room',
                },
              ],
            }
          : s,
      ),
    }
    localStorage.setItem('oqim:v2', JSON.stringify(state))
    return id
  }

  it('opens a locally stored PDF from the blob store', async () => {
    const user = userEvent.setup()
    const openSpy = vi.fn(() => ({}) as Window)
    vi.stubGlobal('open', openSpy)
    seam.blobs.set('attachment:deck', new Blob(['%PDF-1.4'], { type: 'application/pdf' }))
    const id = seedVcWithUploads()
    renderAt(`/app/startups/${id}`)

    await user.click(screen.getByRole('button', { name: 'uploaded-real-deck.pdf faylini ochish' }))

    expect(seam.getBlob).toHaveBeenCalledWith('attachment:deck')
    expect(URL.createObjectURL).toHaveBeenCalled()
    expect(openSpy).toHaveBeenCalledWith('blob:mock-url', '_blank', 'noopener')
    vi.unstubAllGlobals()
  })

  it('downloads a locally stored PDF via a temporary anchor with the original filename', async () => {
    const user = userEvent.setup()
    const openSpy = vi.fn(() => ({}) as Window)
    vi.stubGlobal('open', openSpy)
    // Capture the anchor's state at click time — it must already carry the
    // object URL + filename and be attached to the document.
    let clickedAnchor: { href: string; download: string; connected: boolean } | null = null
    const anchorClick = vi
      .spyOn(HTMLAnchorElement.prototype, 'click')
      .mockImplementation(function (this: HTMLAnchorElement) {
        clickedAnchor = { href: this.href, download: this.download, connected: this.isConnected }
      })
    seam.blobs.set('attachment:deck', new Blob(['%PDF-1.4'], { type: 'application/pdf' }))
    const id = seedVcWithUploads()
    renderAt(`/app/startups/${id}`)

    const button = screen.getByRole('button', {
      name: 'uploaded-real-deck.pdf faylini yuklab olish',
    })
    expect(button).toHaveTextContent('Yuklab olish')
    await user.click(button)

    expect(seam.getBlob).toHaveBeenCalledWith('attachment:deck')
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1)
    expect(anchorClick).toHaveBeenCalledTimes(1)
    expect(clickedAnchor).toEqual({
      href: 'blob:mock-url',
      download: 'uploaded-real-deck.pdf',
      connected: true,
    })
    // Cleanup: the helper anchor is gone and the object URL is released.
    expect(document.querySelector('a[download]')).toBeNull()
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:mock-url')
    // Download never opens a tab — that stays the Open action's job.
    expect(openSpy).not.toHaveBeenCalled()
    anchorClick.mockRestore()
    vi.unstubAllGlobals()
  })

  it('reports a missing blob instead of claiming the file downloaded', async () => {
    const user = userEvent.setup()
    const anchorClick = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const id = seedVcWithUploads() // seam.blobs left empty on purpose
    renderAt(`/app/startups/${id}`)

    await user.click(
      screen.getByRole('button', { name: 'uploaded-real-deck.pdf faylini yuklab olish' }),
    )

    expect(await screen.findByText(/Faylni yuklab olib bo'lmadi/)).toBeInTheDocument()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
    expect(URL.revokeObjectURL).not.toHaveBeenCalled()
    expect(anchorClick).not.toHaveBeenCalled()
    anchorClick.mockRestore()
  })

  it('reports a missing blob instead of claiming the file opened', async () => {
    const user = userEvent.setup()
    const id = seedVcWithUploads() // seam.blobs left empty on purpose
    renderAt(`/app/startups/${id}`)

    await user.click(screen.getByRole('button', { name: 'uploaded-real-deck.pdf faylini ochish' }))
    expect(await screen.findByText(/Faylni ochib bo'lmadi/)).toBeInTheDocument()
    expect(URL.createObjectURL).not.toHaveBeenCalled()
  })

  it('keeps seeded metadata readable and links only http(s) data-room URLs', () => {
    const id = seedVcWithUploads()
    renderAt(`/app/startups/${id}`)

    // Seeded demo attachments have no storageKey → plain metadata, no action.
    expect(screen.getByText(/xarid-seed-deck\.pdf/)).toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: 'xarid-seed-deck.pdf faylini ochish' }),
    ).not.toBeInTheDocument()

    // Uploaded PDF shows a human-readable size.
    expect(screen.getByText(/2\.3 MB/)).toBeInTheDocument()

    // Only the schemeful https URL becomes a link; the bare seeded one stays text.
    const links = screen.getAllByRole('link', { name: 'Havolani ochish' })
    expect(links).toHaveLength(1)
    expect(links[0]).toHaveAttribute('href', 'https://drive.example.com/room')
    expect(links[0]).toHaveAttribute('rel', 'noopener noreferrer')
    expect(links[0]).toHaveAttribute('target', '_blank')
    expect(screen.getByText(/drive\.google\.com\/xarid-dataroom/)).toBeInTheDocument()
  })
})
