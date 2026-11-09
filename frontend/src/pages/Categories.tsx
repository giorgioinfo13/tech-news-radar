import type { UiMessage } from '../messages'
import { message } from '../messages'
import { useLanguage } from '../language-context'
import { usePanelFocus } from '../usePanelFocus'
import { useState, type FormEvent } from 'react'
import { errorMessage, mutate, type Category } from '../api'
import { ConfirmDialog, Empty, Notice } from '../components'

function CategoryEditor({
  category,
  busy,
  onSave,
  onCancel,
}: {
  category?: Category
  busy: boolean
  onSave: (input: Omit<Category, 'id'>) => void
  onCancel: () => void
}) {
  const { t } = useLanguage()
  const panelRef = usePanelFocus()
  const [name, setName] = useState(category?.name ?? '')
  const [slug, setSlug] = useState(category?.slug ?? '')
  const [order, setOrder] = useState(category?.sort_order ?? 0)
  const [error, setError] = useState<UiMessage | ''>('')
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setError(message('Enter a category name.'))
      return
    }
    onSave({ name: name.trim(), slug: slug.trim(), sort_order: order })
  }
  return (
    <section
      ref={panelRef}
      tabIndex={-1}
      className="editor-panel"
      aria-labelledby="category-editor-title"
    >
      <h2 id="category-editor-title">{category ? t('Edit category') : t('Add a category')}</h2>
      <form onSubmit={submit}>
        <fieldset className="form-grid" disabled={busy}>
          <label>
            {t('Category name')}
            <input
              name="category-name"
              autoComplete="off"
              required
              maxLength={120}
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <div>
            <label>
              {t('Identifier')}
              <input
                required
                maxLength={120}
                name="slug"
                autoComplete="off"
                spellCheck={false}
                pattern="[a-z0-9]+(-[a-z0-9]+)*"
                aria-describedby="slug-hint"
                value={slug}
                onChange={(event) => setSlug(event.target.value)}
              />
            </label>
            <p id="slug-hint" className="form-hint">
              {t('Lowercase letters, numbers and hyphens, for example: ai-research.')}
            </p>
          </div>
          <div>
            <label>
              {t('Order')}
              <input
                type="number"
                name="sort-order"
                autoComplete="off"
                required
                min={-2147483648}
                max={2147483647}
                step={1}
                aria-describedby="order-hint"
                value={order}
                onChange={(event) => setOrder(Number(event.target.value))}
              />
            </label>
            <p id="order-hint" className="form-hint">
              {t('Lower numbers appear first.')}
            </p>
          </div>
          {error && (
            <div className="full-width">
              <Notice error>{t(error)}</Notice>
            </div>
          )}
          <div className="actions full-width">
            <button type="submit" className="primary">
              {busy ? t('Saving…') : t('Save category')}
            </button>
            <button type="button" onClick={onCancel}>
              {t('Cancel')}
            </button>
          </div>
        </fieldset>
      </form>
    </section>
  )
}

export function Categories({
  categories,
  onChange,
}: {
  categories: Category[]
  onChange: () => void
}) {
  const { t } = useLanguage()
  const [editor, setEditor] = useState<Category | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Category | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<UiMessage | ''>('')
  const [notice, setMessage] = useState<UiMessage | ''>('')
  async function action(operation: () => Promise<unknown>, success: UiMessage, done: () => void) {
    setBusy(true)
    setError('')
    setMessage('')
    try {
      await operation()
      done()
      setMessage(success)
      onChange()
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <header className="page-header">
        <div>
          <h1>{t('Categories')}</h1>
          <p>{t('Organize sources by topic to find news more easily.')}</p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={() => {
            setEditor('new')
            setError('')
          }}
        >
          {t('Add category')}
        </button>
      </header>
      {notice && <Notice>{t(notice)}</Notice>}
      {error && !deleting && <Notice error>{t(error)}</Notice>}
      {editor && (
        <CategoryEditor
          key={editor === 'new' ? 'new' : editor.id}
          category={editor === 'new' ? undefined : editor}
          busy={busy}
          onCancel={() => setEditor(null)}
          onSave={(input) =>
            void action(
              () =>
                mutate(
                  editor === 'new' ? '/categories' : `/categories/${editor.id}`,
                  editor === 'new' ? 'POST' : 'PATCH',
                  input,
                ),
              message('Category saved.'),
              () => setEditor(null),
            )
          }
        />
      )}
      <div className="section-heading">
        <h2>
          {t('Your categories')} <span>{categories.length}</span>
        </h2>
      </div>
      {!categories.length ? (
        <Empty title={t('Make room for your interests')}>
          {t(
            'Create a category and assign it to your sources. Sources can also remain uncategorized.',
          )}
        </Empty>
      ) : (
        <div className="category-list">
          {categories.map((category) => (
            <article key={category.id} className="category-card">
              <div className="category-info">
                <h3>{category.name}</h3>
                <p>
                  {category.slug} {t('· Order')} {category.sort_order}
                </p>
              </div>
              <div className="actions">
                <button
                  disabled={busy}
                  aria-label={t('Edit {name}', { name: category.name })}
                  onClick={() => {
                    setEditor(category)
                    setError('')
                  }}
                >
                  {t('Edit')}
                </button>
                <button
                  disabled={busy}
                  className="text-danger"
                  aria-label={t('Delete {name}', { name: category.name })}
                  onClick={() => {
                    setDeleting(category)
                    setError('')
                  }}
                >
                  {t('Delete')}
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {deleting && (
        <ConfirmDialog
          title={t('Delete {name}?', { name: deleting.name })}
          pending={busy}
          error={error}
          onCancel={() => {
            setDeleting(null)
            setError('')
          }}
          onConfirm={() =>
            void action(
              () => mutate(`/categories/${deleting.id}`, 'DELETE'),
              message('Category deleted.'),
              () => {
                setDeleting(null)
                setEditor(null)
              },
            )
          }
        >
          {t('Assigned sources will become uncategorized. Articles and sources will be kept.')}
        </ConfirmDialog>
      )}
    </>
  )
}
