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
  const panelRef = usePanelFocus()
  const [name, setName] = useState(category?.name ?? '')
  const [slug, setSlug] = useState(category?.slug ?? '')
  const [order, setOrder] = useState(category?.sort_order ?? 0)
  const [error, setError] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    if (!name.trim()) {
      setError('Inserisci il nome della categoria.')
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
      <h2 id="category-editor-title">
        {category ? 'Modifica categoria' : 'Aggiungi una categoria'}
      </h2>
      <form onSubmit={submit}>
        <fieldset className="form-grid" disabled={busy}>
          <label>
            Nome della categoria
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
              Identificativo
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
              Lettere minuscole, numeri e trattini, ad esempio: ricerca-ai.
            </p>
          </div>
          <div>
            <label>
              Ordine
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
              I numeri più piccoli vengono mostrati prima.
            </p>
          </div>
          {error && (
            <div className="full-width">
              <Notice error>{error}</Notice>
            </div>
          )}
          <div className="actions full-width">
            <button type="submit" className="primary">
              {busy ? 'Salvataggio…' : 'Salva categoria'}
            </button>
            <button type="button" onClick={onCancel}>
              Annulla
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
  const [editor, setEditor] = useState<Category | 'new' | null>(null)
  const [deleting, setDeleting] = useState<Category | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  async function action(operation: () => Promise<unknown>, success: string, done: () => void) {
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
          <h1>Categorie</h1>
          <p>Organizza le fonti per argomento e ritrova le notizie più facilmente.</p>
        </div>
        <button
          className="primary"
          disabled={busy}
          onClick={() => {
            setEditor('new')
            setError('')
          }}
        >
          Aggiungi categoria
        </button>
      </header>
      {message && <Notice>{message}</Notice>}
      {error && !deleting && <Notice error>{error}</Notice>}
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
              'Categoria salvata.',
              () => setEditor(null),
            )
          }
        />
      )}
      <div className="section-heading">
        <h2>
          Le tue categorie <span>{categories.length}</span>
        </h2>
      </div>
      {!categories.length ? (
        <Empty title="Spazio ai tuoi interessi">
          Crea una categoria e assegnala alle tue fonti. Le fonti possono anche restare senza
          categoria.
        </Empty>
      ) : (
        <div className="category-list">
          {categories.map((category) => (
            <article key={category.id} className="category-card">
              <div className="category-info">
                <h3>{category.name}</h3>
                <p>
                  {category.slug} · Ordine {category.sort_order}
                </p>
              </div>
              <div className="actions">
                <button
                  disabled={busy}
                  aria-label={`Modifica ${category.name}`}
                  onClick={() => {
                    setEditor(category)
                    setError('')
                  }}
                >
                  Modifica
                </button>
                <button
                  disabled={busy}
                  className="text-danger"
                  aria-label={`Elimina ${category.name}`}
                  onClick={() => {
                    setDeleting(category)
                    setError('')
                  }}
                >
                  Elimina
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
      {deleting && (
        <ConfirmDialog
          title={`Eliminare ${deleting.name}?`}
          pending={busy}
          error={error}
          onCancel={() => {
            setDeleting(null)
            setError('')
          }}
          onConfirm={() =>
            void action(
              () => mutate(`/categories/${deleting.id}`, 'DELETE'),
              'Categoria eliminata.',
              () => {
                setDeleting(null)
                setEditor(null)
              },
            )
          }
        >
          Le fonti assegnate resteranno senza categoria. Gli articoli e le fonti verranno
          conservati.
        </ConfirmDialog>
      )}
    </>
  )
}
