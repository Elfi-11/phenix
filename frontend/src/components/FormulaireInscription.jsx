import { useState } from 'react'
import { Link, useNavigate } from 'react-router'

function FormulaireInscription() {
    const navigate = useNavigate()
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [erreur, setErreur] = useState(null)

    async function handleSubmit(e) {
        e.preventDefault()
        setErreur(null)

        const res = await fetch('/api/auth/register', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
        })

        if (!res.ok) {
            if (res.status === 409) {
                setErreur("Ce nom d'utilisateur est déjà pris")
            } else {
                setErreur('3 à 50 caractères (lettres, chiffres, _) et mot de passe de 8 caractères minimum')
            }
            return
        }

        // Compte créé : retour à la connexion
        navigate('/')
    }

    return (
        <div className="max-w-sm w-full p-8 rounded-2xl border-2 border-amber-50 shadow-2xl shadow-orange-500/40 bg-linear-to-br from-amber-400 via-orange-600 to-red-900">
            <form onSubmit={handleSubmit}>
                <h1 className="mb-6 text-2xl font-bold text-center text-white drop-shadow">Créer un compte</h1>

                <div className="mb-5">
                    <label htmlFor="username" className="block mb-2 text-sm font-medium text-white">
                        Nom d'utilisateur
                    </label>
                    <input
                        type="text"
                        id="username"
                        className="block w-full px-3 py-2.5 text-sm text-white bg-black/40 border border-amber-300/50 rounded-lg placeholder:text-orange-100/60 focus:outline-none focus:ring-2 focus:ring-amber-300"
                        placeholder="Nom Utilisateur"
                        required
                        minLength={3}
                        maxLength={50}
                        pattern="[a-zA-Z0-9_]+"
                        title="Lettres, chiffres et _ uniquement"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                    />
                </div>

                <div className="mb-6">
                    <label htmlFor="password" className="block mb-2 text-sm font-medium text-white">
                        Mot de passe
                    </label>
                    <input
                        type="password"
                        id="password"
                        className="block w-full px-3 py-2.5 text-sm text-white bg-black/40 border border-amber-300/50 rounded-lg placeholder:text-orange-100/60 focus:outline-none focus:ring-2 focus:ring-amber-300"
                        placeholder="8 caractères minimum"
                        required
                        minLength={8}
                        maxLength={72}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                    />
                </div>

                {erreur && <p className="mb-4 text-sm font-medium text-amber-100">{erreur}</p>}

                <button
                    type="submit"
                    className="w-full px-4 py-2.5 text-sm font-semibold text-white rounded-lg shadow-lg bg-linear-to-r from-red-700 to-orange-500 hover:from-red-800 hover:to-orange-600 focus:outline-none focus:ring-4 focus:ring-amber-300/60 transition-colors"
                >
                    Créer mon compte
                </button>

                <Link to="/" className="block mt-4 text-sm text-center text-amber-100 underline hover:text-white">
                    Déjà un compte ? Se connecter
                </Link>
            </form>
        </div>
    )
}

export default FormulaireInscription
