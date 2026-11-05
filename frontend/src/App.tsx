export default function App() {
  return (
    <main className="mx-auto flex min-h-svh max-w-4xl flex-col justify-center px-6 py-16 sm:px-12">
      <div className="mb-8 flex items-center gap-3 text-sm font-semibold tracking-wide text-teal-800">
        <span aria-hidden="true" className="h-3 w-3 rounded-full bg-teal-700" />
        TECH NEWS RADAR
      </div>
      <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-slate-950 sm:text-6xl">
        Your news.<br />Your sources.
      </h1>
      <p className="mt-6 max-w-xl text-lg leading-relaxed text-slate-600">
        A personal space for technology, AI, software development, and economics.
        Built around the sources you choose.
      </p>
      <section aria-labelledby="status-title" className="mt-12 rounded-2xl border border-slate-200 bg-white p-6 sm:p-8">
        <h2 id="status-title" className="text-base font-semibold text-slate-900">A foundation for what comes next</h2>
        <p className="mt-2 max-w-xl leading-relaxed text-slate-600">
          This project is in early development. News collection, your reading list,
          and source management will arrive in future updates.
        </p>
      </section>
      <p className="mt-8 text-sm text-slate-500">Simple by design. Made for curious readers.</p>
    </main>
  )
}
