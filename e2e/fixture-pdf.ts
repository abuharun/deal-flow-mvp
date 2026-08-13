/**
 * A minimal, valid, text-bearing PDF, built byte-for-byte in code.
 *
 * Generated rather than committed so the fixture is reviewable as source and
 * identical on every run. It has to satisfy the real upload path, not just
 * look like a PDF: `backend/app/services/pdf_validation.py` checks the header,
 * that it is not encrypted, and that the page count is 1..15, and the analysis
 * worker later needs pypdf to extract actual text from it — a blank page would
 * fail the run with SNAPSHOT_DECK_NO_TEXT.
 *
 * Deliberately the same construction as the Python helper in
 * backend/tests/integration/test_cli_analysis_worker.py, so the browser
 * uploads exactly the shape the backend suite already exercises.
 */

export const DECK_TEXT = 'Bevosita local E2E pitch deck. One page, extractable text.'

export function buildDeckPdf(text: string = DECK_TEXT): Buffer {
  const content = Buffer.from(`BT /F1 18 Tf 60 700 Td (${text}) Tj ET`, 'latin1')
  const objects: Buffer[] = [
    Buffer.from('<< /Type /Catalog /Pages 2 0 R >>', 'latin1'),
    Buffer.from('<< /Type /Pages /Kids [3 0 R] /Count 1 >>', 'latin1'),
    Buffer.from(
      '<< /Type /Page /Parent 2 0 R /Resources << /Font << /F1 4 0 R >> >> ' +
        '/MediaBox [0 0 612 792] /Contents 5 0 R >>',
      'latin1',
    ),
    Buffer.from('<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>', 'latin1'),
    Buffer.concat([
      Buffer.from(`<< /Length ${content.length} >>\nstream\n`, 'latin1'),
      content,
      Buffer.from('\nendstream', 'latin1'),
    ]),
  ]

  const parts: Buffer[] = [Buffer.from('%PDF-1.4\n', 'latin1')]
  const offsets: number[] = []
  let cursor = parts[0].length
  objects.forEach((object, index) => {
    offsets.push(cursor)
    const chunk = Buffer.concat([
      Buffer.from(`${index + 1} 0 obj\n`, 'latin1'),
      object,
      Buffer.from('\nendobj\n', 'latin1'),
    ])
    parts.push(chunk)
    cursor += chunk.length
  })

  const xrefOffset = cursor
  const xref = [`xref\n0 ${objects.length + 1}\n`, '0000000000 65535 f \n']
    .concat(offsets.map((offset) => `${String(offset).padStart(10, '0')} 00000 n \n`))
    .join('')
  parts.push(Buffer.from(xref, 'latin1'))
  parts.push(
    Buffer.from(
      `trailer << /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xrefOffset}\n%%EOF`,
      'latin1',
    ),
  )
  return Buffer.concat(parts)
}
