/** Authentication state: the signed-in user, their permissions and the
 *  sign-in / sign-out actions.
 *
 *  Permissions come from the server (`GET /api/auth/permissions`), which
 *  reads the same role map the endpoints enforce. Hiding a button the
 *  user cannot use is a courtesy; the server refusing the call is the
 *  actual control, so nothing here is a security boundary.
 */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

import { setUnauthorisedHandler, tokenStore, userStore } from '../services/api.js'
import { authApi } from '../services/endpoints.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => userStore.get())
  const [permissions, setPermissions] = useState([])
  const [status, setStatus] = useState('loading') // loading | signed-in | signed-out
  const [sessionExpired, setSessionExpired] = useState(false)

  const signOut = useCallback((options = {}) => {
    tokenStore.clear()
    setUser(null)
    setPermissions([])
    setStatus('signed-out')
    setSessionExpired(Boolean(options.expired))
  }, [])

  // Any 401 from a non-login request means the token is gone or stale.
  useEffect(() => {
    setUnauthorisedHandler(() => signOut({ expired: true }))
    return () => setUnauthorisedHandler(null)
  }, [signOut])

  // Re-validate a stored token on first load: it may have expired while
  // the tab was closed, and a stale localStorage user must not be trusted.
  useEffect(() => {
    let cancelled = false

    async function restore() {
      if (!tokenStore.get()) {
        setStatus('signed-out')
        return
      }
      try {
        const [profile, perms] = await Promise.all([authApi.me(), authApi.permissions()])
        if (cancelled) return
        setUser(profile)
        userStore.set(profile)
        setPermissions(perms.permissions)
        setStatus('signed-in')
      } catch {
        if (!cancelled) signOut()
      }
    }

    restore()
    return () => {
      cancelled = true
    }
  }, [signOut])

  const signIn = useCallback(async (email, password) => {
    const result = await authApi.login(email, password)
    tokenStore.set(result.access_token)
    userStore.set(result.user)
    setUser(result.user)
    setPermissions(result.permissions)
    setStatus('signed-in')
    setSessionExpired(false)
    return result
  }, [])

  const value = useMemo(() => {
    const granted = new Set(permissions)
    return {
      user,
      permissions,
      status,
      sessionExpired,
      signIn,
      signOut,
      isSignedIn: status === 'signed-in' && Boolean(user),
      /** True when the role holds every permission listed. */
      can: (...required) => required.every((permission) => granted.has(permission)),
      /** True when the role holds at least one of the permissions listed. */
      canAny: (...required) => required.some((permission) => granted.has(permission)),
    }
  }, [user, permissions, status, sessionExpired, signIn, signOut])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside an <AuthProvider>')
  }
  return context
}
