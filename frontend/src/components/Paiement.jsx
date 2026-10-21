import { useEffect, useState } from 'react'

// Compte du marchand de démo 
const MARCHAND_ACCOUNT_ID = 3

// Identifiant unique par paiement, évite les doublons
function nouvelleCle() {
    return crypto.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`
}

function Paiement({ token }) {
    const [solde, setSolde] = useState(null)
    const [montant, setMontant] = useState('')
    const [message, setMessage] = useState(null)
    const [refresh, setRefresh] = useState(0)
    const [envoi, setEnvoi] = useState(false) // bloque le double clic pendant l'envoi

    useEffect(() => {
        async function chargerSolde() {
            try {
                const res = await fetch('/api/accounts/me', {
                    headers: { Authorization: `Bearer ${token}` },
                    cache: 'no-store',
                })
                if (!res.ok) {
                    setSolde(false)
                    return
                }
                const data = await res.json()
                setSolde(data.balance)
            } catch {
                setSolde(false)
            }
        }

        chargerSolde()
    }, [token, refresh])

    async function handlePayer(e) {
        e.preventDefault()
        setMessage(null)
        setEnvoi(true)

        try {
            const res = await fetch('/api/transactions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    Authorization: `Bearer ${token}`,
                },
                body: JSON.stringify({
                    idempotency_key: nouvelleCle(),
                    receiver_account_id: MARCHAND_ACCOUNT_ID,
                    amount: montant,
                }),
            })

            if (res.ok) {
                setMessage('Paiement réussi')
                setMontant('')
                setRefresh((r) => r + 1) 
            } else {
                const data = await res.json().catch(() => ({}))
                setMessage(typeof data.detail === 'string' ? data.detail : 'Paiement refusé')
            }
        } catch {
            setMessage('Service indisponible, réessayez')
        } finally {
            setEnvoi(false)
        }
    }

    return (
        <div className="max-w-sm w-full p-8 rounded-2xl border-2 border-amber-50 shadow-2xl shadow-orange-500/40 bg-linear-to-br from-amber-400 via-orange-600 to-red-900">
            <h1 className="mb-1 text-2xl font-bold text-center text-white drop-shadow">Paiement</h1>
            <p className="mb-6 text-center text-2xl font-semibold text-white">
                {solde === null ? 'Chargement…' : solde === false ? 'Solde indisponible' : `Solde : ${solde} €`}
            </p>

            <form onSubmit={handlePayer}>
                <label htmlFor="montant" className="block mb-2 text-sm font-medium text-white">
                    Montant à payer au marchand (€)
                </label>
                <input
                    type="number"
                    id="montant"
                    className="block w-full mb-5 px-3 py-2.5 text-sm text-white bg-black/40 border border-amber-300/50 rounded-lg placeholder:text-orange-100/60 focus:outline-none focus:ring-2 focus:ring-amber-300"
                    placeholder="50.00"
                    min="0.01"
                    step="0.01"
                    required
                    value={montant}
                    onChange={(e) => setMontant(e.target.value)}
                />

                {message && <p className="mb-4 text-sm font-medium text-amber-100">{message}</p>}

                <button
                    type="submit"
                    disabled={envoi}
                    className="w-full px-4 py-2.5 text-sm font-semibold text-white rounded-lg shadow-lg bg-linear-to-r from-red-700 to-orange-500 hover:from-red-800 hover:to-orange-600 focus:outline-none focus:ring-4 focus:ring-amber-300/60 transition-colors disabled:opacity-50"
                >
                    {envoi ? 'Paiement en cours…' : 'Payer'}
                </button>
            </form>
        </div>
    )
}

export default Paiement
