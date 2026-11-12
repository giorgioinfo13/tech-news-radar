import { useEffect, useState } from 'react'
import { errorMessage, request, type Page } from '../api'
import { Empty, Pagination, QueryState } from '../components'
import { useLanguage } from '../language-context'
import type { MessageKey, UiMessage } from '../messages'

type UsageState = 'measured' | 'unverified' | 'unavailable'
type AttemptStatus = 'running' | 'success' | 'error' | 'interrupted'
interface Tokens {
  input_tokens: number | null
  output_tokens: number | null
  thought_tokens: number | null
  total_tokens: number | null
  estimated_nano_usd: number | null
  reserved_nano_usd: number
}
interface Summary extends Tokens {
  attempts: number
  successes: number
  measured_attempts: number
  unavailable_attempts: number
  unverified_attempts: number
}
interface Attempt extends Tokens {
  id: string
  started_at: string
  edition_at: string | null
  finished_at: string | null
  dispatched_at: string | null
  model: string
  status: AttemptStatus
  error_code: string | null
  counted_tokens: number | null
  usage_state: UsageState
}
export interface GeminiUsageData {
  month: string
  summary: Summary
  days: (Summary & { day: string })[]
  attempts: Page<Attempt>
  budget_reserved_nano_usd: number
  budget_limit_nano_usd: number
}

const statusLabels: Record<AttemptStatus, MessageKey> = {
  running: 'In progress',
  success: 'Digest saved',
  error: 'Failed attempt',
  interrupted: 'Interrupted attempt',
}
const usageLabels: Record<UsageState, MessageKey> = {
  measured: 'Verified usage',
  unverified: 'Unverified usage',
  unavailable: 'Usage unavailable',
}

export function GeminiUsage() {
  const { t, locale } = useLanguage()
  const [month, setMonth] = useState(() => new Date().toISOString().slice(0, 7))
  const [offset, setOffset] = useState(0)
  const [revision, setRevision] = useState(0)
  const [result, setResult] = useState<{
    key: string
    data?: GeminiUsageData
    error?: UiMessage
  }>()
  const key = `${month}:${offset}:${revision}`
  useEffect(() => {
    const controller = new AbortController()
    request<GeminiUsageData>(`/usage/gemini?month=${month}-01&limit=20&offset=${offset}`, {
      signal: controller.signal,
    }).then(
      (data) => {
        if (!controller.signal.aborted) setResult({ key, data })
      },
      (error) => {
        if (!controller.signal.aborted) setResult({ key, error: errorMessage(error) })
      },
    )
    return () => controller.abort()
  }, [key, month, offset])
  const loading = result?.key !== key
  const data = loading ? undefined : result?.data
  const refresh = () => setRevision((value) => value + 1)
  const number = (value: number | null) =>
    value === null ? t('Not available') : value.toLocaleString(locale)
  const money = (value: number | null) =>
    value === null
      ? t('Not available')
      : new Intl.NumberFormat(locale, {
          style: 'currency',
          currency: 'USD',
          minimumFractionDigits: 6,
          maximumFractionDigits: 6,
        }).format(value / 1_000_000_000)
  const date = (value: string) =>
    new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
      timeZone: 'UTC',
    }).format(new Date(value))
  const tokenDetails = (item: Tokens) => (
    <dl className="ai-usage-values">
      <div>
        <dt>{t('Input tokens')}</dt>
        <dd>{number(item.input_tokens)}</dd>
      </div>
      <div>
        <dt>{t('Output tokens')}</dt>
        <dd>{number(item.output_tokens)}</dd>
      </div>
      <div>
        <dt>{t('Thinking tokens')}</dt>
        <dd>{number(item.thought_tokens)}</dd>
      </div>
      <div>
        <dt>{t('Total tokens')}</dt>
        <dd>{number(item.total_tokens)}</dd>
      </div>
    </dl>
  )
  return (
    <section className="ai-usage" aria-labelledby="gemini-usage-title">
      <div className="page-header">
        <div>
          <h1 id="gemini-usage-title">{t('Gemini statistics')}</h1>
          <p>{t('Tokens and estimated costs for shared AI digests.')}</p>
        </div>
        <button disabled={loading} onClick={refresh}>
          {t('Refresh statistics')}
        </button>
      </div>
      <label className="ai-usage-month">
        {t('Month (UTC)')}
        <input
          type="month"
          min="2000-01"
          max="9998-12"
          value={month}
          onChange={(event) => {
            if (/^\d{4}-(0[1-9]|1[0-2])$/.test(event.target.value) && event.target.validity.valid) {
              setMonth(event.target.value)
              setOffset(0)
            }
          }}
        />
      </label>
      <p className="form-hint">
        {t(
          'Dates use UTC. Reading a saved digest does not generate tokens. Older usage may be unavailable.',
        )}
      </p>
      <QueryState loading={loading} error={loading ? undefined : result?.error} retry={refresh} />
      {data && (
        <>
          <section className="panel ai-usage-section" aria-labelledby="gemini-month-title">
            <h2 id="gemini-month-title">{t('Monthly summary')}</h2>
            <p>
              {t('Attempts: {attempts} · Saved digests: {successes} · Verified usage: {measured}', {
                attempts: data.summary.attempts,
                successes: data.summary.successes,
                measured: data.summary.measured_attempts,
              })}
            </p>
            {tokenDetails(data.summary)}
            <dl className="ai-usage-values">
              <div>
                <dt>{t('Estimated cost')}</dt>
                <dd>{money(data.summary.estimated_nano_usd)}</dd>
              </div>
              <div>
                <dt>{t('Monthly budget reserved')}</dt>
                <dd>{money(data.budget_reserved_nano_usd)}</dd>
              </div>
              <div>
                <dt>{t('Local monthly budget')}</dt>
                <dd>{money(data.budget_limit_nano_usd)}</dd>
              </div>
            </dl>
            <p className="form-hint">
              {t(
                'Totals include verified usage only. Unavailable: {unknown} · Unverified: {unverified}. These are not zero consumption.',
                {
                  unknown: data.summary.unavailable_attempts,
                  unverified: data.summary.unverified_attempts,
                },
              )}
            </p>
            <p className="form-hint">
              {t(
                'Costs are estimates in USD, not invoices or credit balances. Reservations are prudential budget allocations, not actual charges.',
              )}
            </p>
          </section>
          {data.days.length > 0 && (
            <section className="panel ai-usage-section" aria-labelledby="gemini-days-title">
              <h2 id="gemini-days-title">{t('Daily summary')}</h2>
              <div
                className="ai-usage-table"
                role="region"
                aria-labelledby="gemini-days-title"
                tabIndex={0}
              >
                <table>
                  <thead>
                    <tr>
                      {(
                        [
                          'Day (UTC)',
                          'Attempts',
                          'Verified usage',
                          'Total tokens',
                          'Estimated cost',
                        ] as const
                      ).map((label) => (
                        <th scope="col" key={label}>
                          {t(label)}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.days.map((day) => (
                      <tr key={day.day}>
                        <th scope="row">
                          {new Intl.DateTimeFormat(locale, {
                            day: 'numeric',
                            month: 'short',
                            timeZone: 'UTC',
                          }).format(new Date(`${day.day}T00:00:00Z`))}
                        </th>
                        <td>{number(day.attempts)}</td>
                        <td>{number(day.measured_attempts)}</td>
                        <td>{number(day.total_tokens)}</td>
                        <td>{money(day.estimated_nano_usd)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}
          <section className="ai-usage-section" aria-labelledby="gemini-attempts-title">
            <h2 id="gemini-attempts-title">{t('Generation attempts')}</h2>
            {data.attempts.total === 0 && (
              <Empty title={t('No attempts recorded this month.')}>
                {t(
                  'Statistics will appear after the next scheduled generation. Earlier deleted attempts cannot be recovered.',
                )}
              </Empty>
            )}
            {data.attempts.items.map((attempt) => (
              <details className="panel ai-usage-attempt" key={attempt.id}>
                <summary>
                  <span>
                    {date(attempt.started_at)} · {t(statusLabels[attempt.status])}
                  </span>
                  <span>{t(usageLabels[attempt.usage_state])}</span>
                </summary>
                <p className="form-hint">
                  {t('Requested model')}: <span translate="no">{attempt.model}</span>
                </p>
                {attempt.usage_state !== 'measured' && (
                  <p>
                    {t(usageLabels[attempt.usage_state])}.{' '}
                    {t('Excluded from token and cost totals.')}
                  </p>
                )}
                {tokenDetails(attempt)}
                <dl className="ai-usage-values">
                  <div>
                    <dt>{t('Preflight input count')}</dt>
                    <dd>{number(attempt.counted_tokens)}</dd>
                  </div>
                  <div>
                    <dt>{t('Estimated cost')}</dt>
                    <dd>{money(attempt.estimated_nano_usd)}</dd>
                  </div>
                  <div>
                    <dt>{t('Prudential reservation')}</dt>
                    <dd>{money(attempt.reserved_nano_usd)}</dd>
                  </div>
                </dl>
                <dl className="ai-usage-metadata">
                  <div>
                    <dt>{t('Edition (UTC)')}</dt>
                    <dd>{attempt.edition_at ? date(attempt.edition_at) : t('Not available')}</dd>
                  </div>
                  <div>
                    <dt>{t('Dispatch authorized (UTC)')}</dt>
                    <dd>
                      {attempt.dispatched_at ? date(attempt.dispatched_at) : t('Not recorded')}
                    </dd>
                  </div>
                  <div>
                    <dt>{t('Finished (UTC)')}</dt>
                    <dd>{attempt.finished_at ? date(attempt.finished_at) : t('Not recorded')}</dd>
                  </div>
                  <div>
                    <dt>{t('Attempt ID')}</dt>
                    <dd translate="no">{attempt.id}</dd>
                  </div>
                  {attempt.error_code && (
                    <div>
                      <dt>{t('Error code')}</dt>
                      <dd translate="no">{attempt.error_code}</dd>
                    </div>
                  )}
                </dl>
              </details>
            ))}
            {data.attempts.total > 0 && <Pagination {...data.attempts} onChange={setOffset} />}
          </section>
        </>
      )}
    </section>
  )
}
