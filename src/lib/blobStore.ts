/**
 * Focused IndexedDB helper for locally stored attachment bytes (PDFs).
 *
 * Metadata keeps flowing through the existing draft/store/localStorage path;
 * only the raw bytes land here, keyed by a stable per-kind storage key
 * (e.g. `attachment:deck`). Every function rejects when IndexedDB is
 * unavailable or a transaction fails — callers must never report success
 * for bytes that were not actually saved.
 */

const DB_NAME = 'bevosita-attachments'
const DB_VERSION = 1
const STORE_NAME = 'blobs'

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === 'undefined') {
      reject(new Error('IndexedDB is unavailable in this browser'))
      return
    }
    let request: IDBOpenDBRequest
    try {
      request = indexedDB.open(DB_NAME, DB_VERSION)
    } catch (err) {
      reject(err instanceof Error ? err : new Error('IndexedDB open failed'))
      return
    }
    request.onupgradeneeded = () => {
      const db = request.result
      if (!db.objectStoreNames.contains(STORE_NAME)) db.createObjectStore(STORE_NAME)
    }
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
  })
}

async function withStore<T>(
  mode: IDBTransactionMode,
  run: (store: IDBObjectStore) => IDBRequest<T>,
): Promise<T> {
  const db = await openDb()
  try {
    return await new Promise<T>((resolve, reject) => {
      const tx = db.transaction(STORE_NAME, mode)
      const request = run(tx.objectStore(STORE_NAME))
      tx.oncomplete = () => resolve(request.result)
      tx.onabort = () => reject(tx.error ?? new Error('IndexedDB transaction aborted'))
      tx.onerror = () => reject(tx.error ?? request.error ?? new Error('IndexedDB transaction failed'))
    })
  } finally {
    db.close()
  }
}

export async function putBlob(key: string, blob: Blob): Promise<void> {
  await withStore('readwrite', (store) => store.put(blob, key))
}

export async function getBlob(key: string): Promise<Blob | null> {
  const value = await withStore('readonly', (store) => store.get(key))
  return value instanceof Blob ? value : null
}

export async function deleteBlob(key: string): Promise<void> {
  await withStore('readwrite', (store) => store.delete(key))
}
