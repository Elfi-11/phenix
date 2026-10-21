import { useState } from 'react'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router'
import FormulaireConnexion from './components/FormulaireConnexion'
import FormulaireInscription from './components/FormulaireInscription'
import Dashboard from './components/Dashboard'
import Paiement from './components/Paiement'
import fond from './assets/phenixBackground.png'

function App() {
  // Token JWT gardé en mémoire uniquement : perdu au rechargement
  const [token, setToken] = useState(null)
  const [user, setUser] = useState(null)

  // Après le login : on garde le token, puis on demande au backend qui est connecté (dont son rôle)
  async function handleLogin(newToken) {
    setToken(newToken)

    const res = await fetch('/api/auth/me', {
      headers: { Authorization: `Bearer ${newToken}` },
    })
    if (!res.ok) {
      setToken(null)
      return
    }
    setUser(await res.json())
  }

  // Le token n'existe qu'en mémoire : l'effacer suffit à déconnecter (les routes protégées renvoient vers /)
  function handleLogout() {
    setToken(null)
    setUser(null)
  }

  return (
    <BrowserRouter>
      <main
        className="min-h-screen flex items-center justify-center bg-cover bg-center bg-no-repeat"
        style={{ backgroundImage: `url(${fond})` }}
      >
        {/* Visible sur toutes les pages dès qu'on est connecté (client, admin, compte technique) */}
        {user && (
          <button
            type="button"
            onClick={handleLogout}
            className="fixed top-4 right-4 z-10 px-4 py-2 text-sm font-semibold text-white rounded-lg border-2 border-amber-50 bg-black/60 hover:bg-black/80 focus:outline-none focus:ring-4 focus:ring-amber-300/60 transition-colors"
          >
            Se déconnecter ({user.username})
          </button>
        )}
        <Routes>
          <Route
            path="/"
            element={
              !user ? (
                <FormulaireConnexion onLogin={handleLogin} />
              ) : user.role === 'ADMIN' ? (
                <Navigate to="/dashboard" />
              ) : user.role === 'SERVICE' ? (
                // Compte des programmes automatiques : pas d'interface (le backend refuse aussi ses accès métier)
                <p className="text-2xl font-bold text-white drop-shadow">Compte technique : pas d'accès à l'interface</p>
              ) : (
                // Un seul élément par branche : le message et la carte sont regroupés dans une colonne
                <div className="flex flex-col items-center gap-4 w-full">
                  <p className="text-xl font-semibold text-center text-amber-100 drop-shadow">
                    Bonne renaissance, {user.username} 
                  </p>
                  <Paiement token={token} />
                </div>
              )
            }
          />
          <Route path="/inscription" element={<FormulaireInscription />} />
          {/* Réservé aux ADMIN ; user?.role évite une erreur quand user vaut null */}
          <Route
            path="/dashboard"
            element={user?.role === 'ADMIN' ? <Dashboard token={token} /> : <Navigate to="/" />}
          />
        </Routes>
      </main>
    </BrowserRouter>
  )
}

export default App
