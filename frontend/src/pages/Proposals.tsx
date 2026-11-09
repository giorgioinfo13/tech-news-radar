import { useState, type FormEvent } from 'react'
import {
  errorMessage,
  formatDate,
  mutate,
  safeArticleUrl,
  type Category,
  type Source,
  type SourceProposal,
} from '../api'
import { Notice, Pagination, QueryState } from '../components'
import { useLanguage } from '../language-context'
import { message, type UiMessage } from '../messages'
import { useQuery } from '../useQuery'

export function Proposals({
  admin,
  categories,
  sources,
  onChange,
}: {
  admin: boolean
  categories: Category[]
  sources: Source[]
  onChange: () => void
}) {
  const { t, locale } = useLanguage()
  const [offset, setOffset] = useState(0)
  const [filter, setFilter] = useState(admin ? 'pending' : '')
  const proposals = useQuery<SourceProposal>(
    `/proposals?limit=20&offset=${offset}${filter ? `&status=${filter}` : ''}`,
  )
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<UiMessage | ''>('')
  const [notice, setNotice] = useState<UiMessage | ''>('')
  const [editing, setEditing] = useState<SourceProposal | null>(null)
  async function act(path: string, body?: unknown) {
    setBusy(true)
    setError('')
    setNotice('')
    try {
      await mutate(path, 'POST', body)
      setNotice(message('Proposal saved. Check its status below.'))
      setEditing(null)
      proposals.reload()
      onChange()
      return true
    } catch (cause) {
      setError(errorMessage(cause))
      proposals.reload()
      onChange()
      return false
    } finally {
      setBusy(false)
    }
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = event.currentTarget
    const data = new FormData(form)
    if (
      await act('/proposals', {
        name: data.get('name'),
        url: data.get('url') || null,
        note: data.get('note') || null,
        category_id: Number(data.get('category')) || null,
        follow_on_approval: data.has('follow'),
      })
    ) {
      form.reset()
      setOffset(0)
    }
  }
  return (
    <>
      <header className="page-header">
        <div>
          <h1>{admin ? t('Proposals') : t('Suggest a source')}</h1>
          <p>{t('Suggestions need administrator approval before collection starts.')}</p>
        </div>
      </header>
      {!admin && (
        <section className="editor-panel" aria-label={t('Suggest a source')}>
          <form onSubmit={(event) => void submit(event)}>
            <p className="form-hint">
              {t(
                'Only the name is required. You can have up to 5 pending proposals. Avoid personal or confidential information.',
              )}
            </p>
            <fieldset className="form-grid" disabled={busy}>
              <label>
                {t('Name')}
                <input name="name" required maxLength={200} />
              </label>
              <label>
                {t('Website or feed URL (optional)')}
                <input name="url" type="url" maxLength={2048} />
              </label>
              <CategoryField categories={categories} />
              <label>
                {t('Short note (optional)')}
                <textarea name="note" maxLength={500} rows={3} />
              </label>
              <label className="subscription-choice full-width">
                <input type="checkbox" name="follow" />
                {t('Follow this source if approved')}
              </label>
              <div className="actions full-width">
                <button className="primary" type="submit">
                  {busy ? t('Saving…') : t('Send proposal')}
                </button>
              </div>
            </fieldset>
          </form>
        </section>
      )}
      {error && <Notice error>{t(error)}</Notice>}
      {notice && <Notice>{t(notice)}</Notice>}
      <section aria-labelledby="proposal-list-title">
        <div className="page-header">
          <h2 id="proposal-list-title">{admin ? t('Source proposals') : t('My proposals')}</h2>
          <button
            disabled={busy || proposals.loading}
            onClick={() => {
              proposals.reload()
              onChange()
            }}
          >
            {t('Refresh list')}
          </button>
        </div>
        <label>
          {t('Status')}
          <select
            value={filter}
            onChange={(e) => {
              setFilter(e.target.value)
              setOffset(0)
              setEditing(null)
            }}
          >
            <option value="">{t('All proposals')}</option>
            <option value="pending">{t('Pending')}</option>
            <option value="approved">{t('Approved')}</option>
            <option value="rejected">{t('Rejected')}</option>
            <option value="cancelled">{t('Canceled')}</option>
          </select>
        </label>
        <QueryState loading={proposals.loading} error={proposals.error} retry={proposals.reload} />
        {proposals.data?.items.length === 0 && (
          <p className="empty">{t('No proposals to show.')}</p>
        )}
        {proposals.data?.items.map((proposal) => (
          <article className="proposal-card" key={proposal.id}>
            <h3>{proposal.name}</h3>
            <p className="muted">
              {t(
                (
                  {
                    pending: 'Pending',
                    approved: 'Approved',
                    rejected: 'Rejected',
                    cancelled: 'Canceled',
                  } as const
                )[proposal.status],
              )}{' '}
              · {formatDate(proposal.created_at, locale)}
              {admin && ` · ${proposal.user.display_name}`}
            </p>
            {proposal.url && (
              <p>
                {safeArticleUrl(proposal.url) ? (
                  <a
                    href={safeArticleUrl(proposal.url)!}
                    target="_blank"
                    rel="noopener noreferrer"
                    referrerPolicy="no-referrer"
                  >
                    {proposal.url}
                  </a>
                ) : (
                  proposal.url
                )}
              </p>
            )}
            {proposal.note && <p>{proposal.note}</p>}
            <p className="muted">
              {t('Suggested category')}:{' '}
              {categories.find((c) => c.id === proposal.category_id)?.name ?? t('Uncategorized')}
            </p>
            <p className="muted">
              {proposal.follow_on_approval
                ? t('Follow on approval requested')
                : t('No automatic subscription requested')}
            </p>
            {proposal.decided_at && (
              <p>
                {t('Decision date')}: {formatDate(proposal.decided_at, locale)}
              </p>
            )}
            {proposal.reason && (
              <p>
                {t('Reason')}: {proposal.reason}
              </p>
            )}
            {proposal.approved_name && (
              <p>
                {t('Approved source')}: {proposal.approved_name}
                {!proposal.source_id && ` · ${t('Source removed from the catalog')}`}
              </p>
            )}
            {proposal.status === 'pending' &&
              (admin ? (
                <button disabled={busy} onClick={() => setEditing(proposal)}>
                  {t('Review proposal')}
                </button>
              ) : (
                <button
                  disabled={busy}
                  onClick={() => void act(`/proposals/${proposal.id}/cancel`)}
                >
                  {t('Cancel proposal')}
                </button>
              ))}
            {admin && editing?.id === proposal.id && (
              <Review
                key={proposal.id}
                proposal={proposal}
                categories={categories}
                sources={sources}
                busy={busy}
                act={act}
              />
            )}
          </article>
        ))}
        {proposals.data && (
          <Pagination
            offset={offset}
            total={proposals.data.total}
            limit={20}
            onChange={setOffset}
          />
        )}
      </section>
    </>
  )
}

function CategoryField({ categories, value }: { categories: Category[]; value?: number | null }) {
  const { t } = useLanguage()
  return (
    <label>
      {t('Suggested category')}
      <select name="category" defaultValue={value ?? ''}>
        <option value="">{t('Uncategorized')}</option>
        {categories.map((c) => (
          <option value={c.id} key={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </label>
  )
}

function Review({
  proposal,
  categories,
  sources,
  busy,
  act,
}: {
  proposal: SourceProposal
  categories: Category[]
  sources: Source[]
  busy: boolean
  act: (path: string, body: unknown) => Promise<boolean>
}) {
  const { t } = useLanguage()
  const [existing, setExisting] = useState('')
  return (
    <div className="editor-panel">
      <form
        onSubmit={(event) => {
          event.preventDefault()
          const data = new FormData(event.currentTarget)
          void act(
            `/proposals/${proposal.id}/approve`,
            existing
              ? { source_id: Number(existing) }
              : {
                  name: data.get('name'),
                  feed_url: data.get('feed'),
                  category_id: Number(data.get('category')) || null,
                },
          )
        }}
      >
        <p className="form-hint">
          {t(
            'Approve explicitly: a new source needs a valid RSS/Atom feed. Linking an existing source keeps its settings, including paused collection.',
          )}
        </p>
        <fieldset disabled={busy} className="form-grid">
          <label className="full-width">
            {t('Link an existing source')}
            <select value={existing} onChange={(e) => setExisting(e.target.value)}>
              <option value="">{t('Create a new source')}</option>
              {sources.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          </label>
          {!existing && (
            <>
              <label>
                {t('Name')}
                <input name="name" defaultValue={proposal.name} required maxLength={200} />
              </label>
              <label>
                {t('RSS/Atom feed URL')}
                <input
                  name="feed"
                  type="url"
                  defaultValue={proposal.url ?? ''}
                  required
                  maxLength={2048}
                />
              </label>
              <CategoryField categories={categories} value={proposal.category_id} />
            </>
          )}
          <div className="actions full-width">
            <button className="primary" type="submit">
              {busy ? t('Saving…') : t('Approve proposal')}
            </button>
          </div>
        </fieldset>
      </form>
      <form
        onSubmit={(event) => {
          event.preventDefault()
          void act(`/proposals/${proposal.id}/reject`, {
            reason: new FormData(event.currentTarget).get('reason'),
          })
        }}
      >
        <fieldset disabled={busy} className="form-grid">
          <label className="full-width">
            {t('Reason for rejection')}
            <textarea name="reason" required maxLength={500} rows={2} />
          </label>
          <div className="actions">
            <button type="submit">{t('Reject proposal')}</button>
          </div>
        </fieldset>
      </form>
    </div>
  )
}
