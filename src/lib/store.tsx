import { createContext, useContext, useEffect, useMemo, useReducer, type ReactNode } from 'react'
import type {
  AppState,
  Attachment,
  Decision,
  Lang,
  Payment,
  Role,
  Signal,
  Stage,
  Startup,
  StepKey,
  SubmissionDraft,
} from './types'
import { STEP_KEYS } from './types'
import { seedStartups, makeVerification, FOUNDER_NAME, FOUNDER_EMAIL, VC_NAME, VC_EMAIL, VALIDATION_FEE } from './seed'
import { summarizeDraft, recommendFromDraft, opaqueId } from './simulate'
import { composeVerdict } from './compose'
import { formatDateLong, DECISION_STAGE } from './format'

/**
 * v2 = Uzbek-localized seed content. Bumping the key retires stale English
 * state persisted by earlier deploys; loadState migrates only the session.
 */
const STORAGE_KEY = 'oqim:v2'
const LEGACY_STORAGE_KEYS = ['oqim:v1']

export function emptyDraft(): SubmissionDraft {
  const fields = {} as Record<StepKey, string>
  for (const k of STEP_KEYS) fields[k] = ''
  return {
    fields,
    startupName: '',
    oneLiner: '',
    sector: '',
    fundingStage: '',
    revenue: '',
    growth: '',
    ask: '',
    attachments: [],
    completed: [],
    updatedAt: null,
  }
}

export function initialState(): AppState {
  return {
    session: null,
    startups: seedStartups(),
    draft: emptyDraft(),
    founderStartupId: null,
    payments: [],
  }
}

export function loadState(): AppState {
  try {
    const rawJson = localStorage.getItem(STORAGE_KEY)
    if (rawJson) {
      const parsed = JSON.parse(rawJson) as AppState
      if (!Array.isArray(parsed.startups) || !parsed.draft) return initialState()
      return parsed
    }
    // Older schema found: keep the user logged in, replace the stale English
    // content with the current (Uzbek) seed, and retire the old key.
    for (const key of LEGACY_STORAGE_KEYS) {
      const legacyJson = localStorage.getItem(key)
      if (!legacyJson) continue
      localStorage.removeItem(key)
      const legacy = JSON.parse(legacyJson) as Partial<AppState>
      const role = legacy?.session?.role
      if (legacy.session && (role === 'founder' || role === 'vc')) {
        return { ...initialState(), session: legacy.session }
      }
    }
    return initialState()
  } catch {
    return initialState()
  }
}

type Action =
  | { type: 'login'; role: Role }
  | { type: 'logout' }
  | { type: 'update-draft'; patch: Partial<SubmissionDraft>; fields?: Partial<Record<StepKey, string>> }
  | { type: 'complete-step'; step: StepKey }
  | { type: 'payment'; ok: boolean }
  | { type: 'patch-startup'; id: string; patch: Partial<Startup> }
  | { type: 'toggle-verification'; id: string; itemId: string }
  | { type: 'compose-verdict'; id: string }
  | { type: 'edit-verdict'; id: string; en: string }
  | { type: 'send-verdict'; id: string }
  | { type: 'reset' }

function patchStartup(state: AppState, id: string, patch: Partial<Startup>): AppState {
  return { ...state, startups: state.startups.map((s) => (s.id === id ? { ...s, ...patch } : s)) }
}

/** Build the founder's Startup record from a completed submission draft. */
export function startupFromDraft(draft: SubmissionDraft, submittedAt: string): Startup {
  const recommendation = recommendFromDraft(draft)
  return {
    id: opaqueId(`founder-${draft.startupName.toLowerCase() || 'untitled'}`),
    name: draft.startupName || 'Nomsiz startap',
    oneLiner: draft.oneLiner || 'Bir qatorli tavsif kiritilmagan',
    sector: draft.sector || "Ko'rsatilmagan",
    fundingStage: draft.fundingStage || "Ko'rsatilmagan",
    founder: { name: FOUNDER_NAME, email: FOUNDER_EMAIL, city: 'Toshkent', language: 'uz' },
    submittedAt,
    stage: 'new',
    signal: recommendation.signal,
    signalOverridden: false,
    summary: summarizeDraft(draft),
    raw: { ...draft.fields },
    metrics: {
      revenue: draft.revenue || "Ko'rsatilmagan",
      growth: draft.growth || "Ko'rsatilmagan",
      ask: draft.ask.split(/[.\n]/)[0]?.trim() || "Ko'rsatilmagan",
    },
    recommendation,
    attachments: draft.attachments,
    verification: makeVerification(),
    decision: null,
    notes: '',
    verdict: null,
  }
}

export function reducer(state: AppState, action: Action): AppState {
  switch (action.type) {
    case 'login': {
      const session =
        action.role === 'founder'
          ? { role: 'founder' as const, name: FOUNDER_NAME, email: FOUNDER_EMAIL }
          : { role: 'vc' as const, name: VC_NAME, email: VC_EMAIL }
      return { ...state, session }
    }
    case 'logout':
      return { ...state, session: null }
    case 'update-draft': {
      const draft: SubmissionDraft = {
        ...state.draft,
        ...action.patch,
        fields: { ...state.draft.fields, ...(action.fields ?? {}) },
        updatedAt: new Date().toISOString(),
      }
      return { ...state, draft }
    }
    case 'complete-step': {
      if (state.draft.completed.includes(action.step)) return state
      return {
        ...state,
        draft: { ...state.draft, completed: [...state.draft.completed, action.step] },
      }
    }
    case 'payment': {
      const payment: Payment = {
        id: `pay_${state.payments.length + 1}`,
        label: `Baholash to'lovi — ${state.draft.startupName || 'ariza'}`,
        amount: VALIDATION_FEE,
        status: action.ok ? 'paid' : 'failed',
        date: new Date().toISOString(),
      }
      if (!action.ok) return { ...state, payments: [...state.payments, payment] }
      const startup = startupFromDraft(state.draft, new Date().toISOString())
      return {
        ...state,
        payments: [...state.payments, payment],
        startups: [startup, ...state.startups.filter((s) => s.id !== startup.id)],
        founderStartupId: startup.id,
      }
    }
    case 'patch-startup':
      return patchStartup(state, action.id, action.patch)
    case 'toggle-verification': {
      const s = state.startups.find((x) => x.id === action.id)
      if (!s) return state
      return patchStartup(state, action.id, {
        verification: s.verification.map((v) => (v.id === action.itemId ? { ...v, done: !v.done } : v)),
      })
    }
    case 'compose-verdict': {
      const s = state.startups.find((x) => x.id === action.id)
      if (!s || !s.decision) return state
      const now = new Date().toISOString()
      const base = {
        decision: s.decision,
        notes: s.notes,
        startupName: s.name,
        founderName: s.founder.name,
        vcName: VC_NAME,
        dateLabel: formatDateLong(now),
      }
      return patchStartup(state, action.id, {
        verdict: {
          decision: s.decision,
          en: composeVerdict({ ...base, lang: 'en' }),
          local: composeVerdict({ ...base, lang: s.founder.language }),
          localLang: s.founder.language,
          composedAt: now,
          sentAt: null,
          edited: false,
        },
      })
    }
    case 'edit-verdict': {
      const s = state.startups.find((x) => x.id === action.id)
      if (!s?.verdict) return state
      return patchStartup(state, action.id, { verdict: { ...s.verdict, en: action.en, edited: true } })
    }
    case 'send-verdict': {
      const s = state.startups.find((x) => x.id === action.id)
      if (!s?.verdict || !s.decision) return state
      return patchStartup(state, action.id, {
        verdict: { ...s.verdict, sentAt: new Date().toISOString() },
        stage: DECISION_STAGE[s.decision],
      })
    }
    case 'reset': {
      const fresh = initialState()
      return { ...fresh, session: state.session }
    }
    default:
      return state
  }
}

interface StoreApi {
  state: AppState
  login: (role: Role) => void
  logout: () => void
  updateDraft: (patch: Partial<SubmissionDraft>, fields?: Partial<Record<StepKey, string>>) => void
  completeStep: (step: StepKey) => void
  pay: (ok: boolean) => void
  moveStage: (id: string, stage: Stage) => void
  setSignal: (id: string, signal: Signal) => void
  toggleVerification: (id: string, itemId: string) => void
  setDecision: (id: string, decision: Decision) => void
  setNotes: (id: string, notes: string) => void
  compose: (id: string) => void
  editVerdict: (id: string, en: string) => void
  sendVerdict: (id: string) => void
  resetDemo: () => void
  founderStartup: Startup | null
  addDraftAttachment: (a: Attachment) => void
  removeDraftAttachment: (fileName: string) => void
}

const StoreContext = createContext<StoreApi | null>(null)

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, undefined, loadState)

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
    } catch {
      // Storage full or unavailable — the demo degrades to in-memory state.
    }
  }, [state])

  const api = useMemo<StoreApi>(() => {
    const founderStartup = state.founderStartupId
      ? state.startups.find((s) => s.id === state.founderStartupId) ?? null
      : null
    return {
      state,
      founderStartup,
      login: (role) => dispatch({ type: 'login', role }),
      logout: () => dispatch({ type: 'logout' }),
      updateDraft: (patch, fields) => dispatch({ type: 'update-draft', patch, fields }),
      completeStep: (step) => dispatch({ type: 'complete-step', step }),
      pay: (ok) => dispatch({ type: 'payment', ok }),
      moveStage: (id, stage) => dispatch({ type: 'patch-startup', id, patch: { stage } }),
      setSignal: (id, signal) =>
        dispatch({ type: 'patch-startup', id, patch: { signal, signalOverridden: true } }),
      toggleVerification: (id, itemId) => dispatch({ type: 'toggle-verification', id, itemId }),
      setDecision: (id, decision) => dispatch({ type: 'patch-startup', id, patch: { decision } }),
      setNotes: (id, notes) => dispatch({ type: 'patch-startup', id, patch: { notes } }),
      compose: (id) => dispatch({ type: 'compose-verdict', id }),
      editVerdict: (id, en) => dispatch({ type: 'edit-verdict', id, en }),
      sendVerdict: (id) => dispatch({ type: 'send-verdict', id }),
      resetDemo: () => dispatch({ type: 'reset' }),
      addDraftAttachment: (a) =>
        dispatch({
          type: 'update-draft',
          patch: { attachments: [...state.draft.attachments.filter((x) => x.fileName !== a.fileName), a] },
        }),
      removeDraftAttachment: (fileName) =>
        dispatch({
          type: 'update-draft',
          patch: { attachments: state.draft.attachments.filter((x) => x.fileName !== fileName) },
        }),
    }
  }, [state])

  return <StoreContext.Provider value={api}>{children}</StoreContext.Provider>
}

export function useStore(): StoreApi {
  const ctx = useContext(StoreContext)
  if (!ctx) throw new Error('useStore must be used inside StoreProvider')
  return ctx
}

export type { Lang }
