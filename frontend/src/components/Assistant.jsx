import { useEffect, useRef, useState } from 'react'

// Le modèle tourne sur CPU : une réponse peut prendre plus d'une minute
const TIMEOUT_MS = 180000

// Chatbox de l'assistant RAG (Ollama + LangChain), réservée à l'ADMIN.
// Contrat attendu : POST /api/assistant/ask { question } -> { status, answer, sources: [{ id, source }] }
function Assistant({ token }) {
  const [messages, setMessages] = useState([]) // { role: 'user' | 'assistant' | 'error', text, sources? }
  const [question, setQuestion] = useState('')
  const [enAttente, setEnAttente] = useState(false)
  const finRef = useRef(null)

  // Fait défiler jusqu'au dernier message
  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [messages, enAttente])

  async function handleEnvoyer(e) {
    e.preventDefault()
    const q = question.trim()
    if (!q) return

    setMessages((m) => [...m, { role: 'user', text: q }])
    setQuestion('')
    setEnAttente(true)

    try {
      const res = await fetch('/api/assistant/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ question: q }),
        signal: AbortSignal.timeout(TIMEOUT_MS),
      })
      const data = await res.json().catch(() => ({}))

      if (!res.ok) {
        const detail = typeof data.detail === 'string' ? data.detail : `erreur ${res.status}`
        setMessages((m) => [...m, { role: 'error', text: `Assistant indisponible (${detail})` }])
      } else if (data.status === 'unverified_citations') {
        // Le RAG refuse une réponse dont il ne peut pas vérifier les sources
        setMessages((m) => [...m, { role: 'error', text: "Réponse non validée : ses sources n'ont pas pu être vérifiées." }])
      } else {
        setMessages((m) => [...m, { role: 'assistant', text: data.answer, sources: data.sources ?? [] }])
      }
    } catch (err) {
      const text = err.name === 'TimeoutError' ? "L'assistant n'a pas répondu à temps." : 'Assistant injoignable.'
      setMessages((m) => [...m, { role: 'error', text }])
    } finally {
      setEnAttente(false)
    }
  }

  return (
    <div className="p-5 rounded-2xl border-2 border-amber-50 bg-[#1a1a19]/95 text-white">
      <h2 className="text-xl font-semibold">Assistant opérateur</h2>
      <p className="mb-4 text-sm text-orange-100/80">
        Répond à partir des procédures de l'équipe. Il conseille, il n'agit pas sur la plateforme.
      </p>

      {/* Historique */}
      <div className="max-h-80 mb-4 space-y-3 overflow-y-auto pr-1" aria-live="polite">
        {messages.length === 0 && (
          <p className="text-sm text-orange-100/60">Exemple : « Comment vérifier la collecte Prometheus ? »</p>
        )}

        {messages.map((m, i) =>
          m.role === 'user' ? (
            <div key={i} className="flex justify-end">
              <p className="max-w-[80%] px-3 py-2 rounded-2xl rounded-br-sm bg-linear-to-r from-red-700 to-orange-500 text-sm">
                {m.text}
              </p>
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div
                className={`max-w-[80%] px-3 py-2 rounded-2xl rounded-bl-sm text-sm border ${
                  m.role === 'error' ? 'bg-black/60 border-red-500/60 text-red-200' : 'bg-black/60 border-amber-50/20'
                }`}
              >
                {/* whitespace-pre-line : garde les retours à la ligne de la réponse */}
                <p className="whitespace-pre-line">{m.text}</p>
                {m.sources?.length > 0 && (
                  <p className="mt-2 text-xs text-orange-100/70">
                    Sources : {m.sources.map((s) => s.source).join(', ')}
                  </p>
                )}
              </div>
            </div>
          ),
        )}

        {enAttente && <p className="text-sm text-orange-100/70 animate-pulse">L'assistant réfléchit… (jusqu'à 1 min)</p>}
        <div ref={finRef} />
      </div>

      {/* Saisie */}
      <form onSubmit={handleEnvoyer} className="flex gap-2">
        <label htmlFor="question" className="sr-only">Question pour l'assistant</label>
        <input
          id="question"
          type="text"
          maxLength={500}
          placeholder="Posez votre question…"
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          disabled={enAttente}
          className="flex-1 px-3 py-2.5 text-sm text-white bg-black/40 border border-amber-300/50 rounded-lg placeholder:text-orange-100/60 focus:outline-none focus:ring-2 focus:ring-amber-300 disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={enAttente || !question.trim()}
          className="px-4 py-2.5 text-sm font-semibold text-white rounded-lg shadow-lg bg-linear-to-r from-red-700 to-orange-500 hover:from-red-800 hover:to-orange-600 focus:outline-none focus:ring-4 focus:ring-amber-300/60 disabled:opacity-50"
        >
          Envoyer
        </button>
      </form>
    </div>
  )
}

export default Assistant
