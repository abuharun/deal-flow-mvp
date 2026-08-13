/**
 * The local-only test accounts, read from the same JSON the Python seed
 * script reads — so the browser can never sign in with credentials that
 * differ from the ones actually written to the database.
 *
 * Read at runtime rather than imported: a JSON `import` would need a Node
 * import attribute, and this keeps one file as the single source of truth
 * for both languages.
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

export interface LocalAccount {
  email: string
  password: string
  full_name: string
}

const file = fileURLToPath(new URL('./local-accounts.json', import.meta.url))
const parsed = JSON.parse(readFileSync(file, 'utf8')) as Record<string, LocalAccount>

export const accounts: Record<'founder' | 'vc', LocalAccount> = {
  founder: parsed.founder,
  vc: parsed.vc,
}
