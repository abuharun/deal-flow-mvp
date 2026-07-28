import type { StepKey } from '../../lib/types'

interface StepMeta {
  title: string
  question: string
  hint: string
  placeholder: string
}

export const STEP_META: Record<StepKey, StepMeta> = {
  problem: {
    title: 'Problem',
    question: 'What problem do you solve, and for whom?',
    hint: 'Be concrete: who feels this pain, how often, and what it costs them today. Plain words beat pitch language.',
    placeholder:
      'e.g. Restaurants in Tashkent buy produce through phone calls and cash at the bazaar. Prices swing 20% week to week and owners cannot see what they spend…',
  },
  product: {
    title: 'Product',
    question: 'What have you built, and how does it solve the problem?',
    hint: 'Describe what actually exists today — not the roadmap. How do customers use it, and how do you make money?',
    placeholder: 'e.g. An ordering app connecting restaurants to vetted wholesale suppliers. One order before 22:00, delivered by 07:00, one invoice. We take 6%…',
  },
  market: {
    title: 'Market',
    question: 'How big is the opportunity?',
    hint: 'Size the market honestly, bottom-up if you can. Who else competes for this money, including "do nothing"?',
    placeholder: 'e.g. 12,000 food-service businesses in Tashkent spending $8–15k/month on procurement — roughly a $600M annual flow…',
  },
  traction: {
    title: 'Traction',
    question: 'What proof do you have that this works?',
    hint: 'Numbers over adjectives: customers, revenue, growth rate, retention. If you are pre-revenue, say so plainly — honesty reads better than spin.',
    placeholder: 'e.g. Live 9 months. 214 restaurants order weekly. GMV last month $412,000, growing 18% month over month. Churn under 3%…',
  },
  team: {
    title: 'Team',
    question: 'Who is building this, and why you?',
    hint: 'Founders, their relevant history, who is full-time, and how ownership is split. Investors fund teams more than ideas.',
    placeholder: 'e.g. CEO ran supply for a café chain for five years; CTO built logistics routing at Uzum. Both full-time, holding 82% combined…',
  },
  ask: {
    title: 'The Ask',
    question: 'How much are you raising, and what will it buy?',
    hint: 'Amount, equity, and what the money achieves. Mention anything already committed.',
    placeholder: 'e.g. Raising $500,000 seed for 12% to expand to two more cities and hire two sales leads. $180,000 already committed…',
  },
}
