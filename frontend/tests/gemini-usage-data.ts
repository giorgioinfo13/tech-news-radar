import type { GeminiUsageData } from '../src/pages/GeminiUsage'
export function usageData(): GeminiUsageData {
  const summary = {
    attempts: 2,
    successes: 1,
    measured_attempts: 1,
    unavailable_attempts: 1,
    unverified_attempts: 0,
    input_tokens: 800,
    output_tokens: 300,
    thought_tokens: 100,
    total_tokens: 1200,
    estimated_nano_usd: 800000,
    reserved_nano_usd: 3250000,
  }
  const attempt = {
    id: '10000000-0000-0000-0000-000000000001',
    started_at: '2026-11-12T10:00:00Z',
    edition_at: '2026-11-12T10:00:00Z',
    dispatched_at: '2026-11-12T10:00:01Z',
    finished_at: '2026-11-12T10:00:10Z',
    model: 'gemini-3.1-flash-lite',
    status: 'success' as const,
    error_code: null,
    counted_tokens: 800,
    usage_state: 'measured' as const,
    input_tokens: 800,
    output_tokens: 300,
    thought_tokens: 100,
    total_tokens: 1200,
    estimated_nano_usd: 800000,
    reserved_nano_usd: 1625000,
  }
  return {
    month: '2026-11-01',
    summary,
    days: [{ ...summary, day: '2026-11-12' }],
    attempts: {
      total: 2,
      offset: 0,
      limit: 20,
      items: [
        attempt,
        {
          ...attempt,
          id: '10000000-0000-0000-0000-000000000002',
          status: 'error',
          usage_state: 'unavailable',
          error_code: 'uncertain',
          input_tokens: null,
          output_tokens: null,
          thought_tokens: null,
          total_tokens: null,
          estimated_nano_usd: null,
        },
      ],
    },
    budget_reserved_nano_usd: 3250000,
    budget_limit_nano_usd: 2000000000,
  }
}
