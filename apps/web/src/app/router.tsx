import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, createBrowserRouter, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import AppLayout from "@/app/layout";
import { api, getAccessToken, onSessionExpired, setAccessToken, BASE_URL } from "@/lib/api";
import { Splash } from "@/components/ui/blur-loading";

// M10 — code splitting: cada página se carga bajo demanda.
const DashboardPage = lazy(() => import("@/features/dashboard/dashboard-page"));
const WalletsPage = lazy(() => import("@/features/wallets/wallets-page"));
const NewOperationPage = lazy(() => import("@/features/transactions/new-operation-page"));
const TransactionsPage = lazy(() => import("@/features/transactions/transactions-page"));
const SavingsPage = lazy(() => import("@/features/savings/savings-page"));
const SubscriptionsPage = lazy(() => import("@/features/subscriptions/subscriptions-page"));
const ProfilePage = lazy(() => import("@/features/profile/profile-page"));
const LoginPage = lazy(() => import("@/features/auth/login-page"));
const RegisterPage = lazy(() => import("@/features/auth/register-page"));
const VerifyPage = lazy(() => import("@/features/auth/verify-page"));
const ForgotPasswordPage = lazy(() => import("@/features/auth/forgot-password-page"));
const ResetPasswordPage = lazy(() => import("@/features/auth/reset-password-page"));

/**
 * Guard de sesión: comprueba si hay una sesión válida (access en memoria o
 * refresh cookie httpOnly) antes de mostrar las rutas privadas.
 *
 * Si no hay access en memoria, intenta refrescar usando la cookie. Si funciona,
 * hace GET /api/auth/me para validar. Si el refresh falla, no hay sesión.
 */
function RequireAuth() {
  const [checking, setChecking] = useState(() => !getAccessToken());
  const [ok, setOk] = useState(() => Boolean(getAccessToken()));

  useEffect(() => {
    if (getAccessToken()) return;
    let cancelled = false;
    (async () => {
      try {
        // Sin access en memoria: intentar refrescar usando la cookie.
        const refreshResp = await fetch(`${BASE_URL}/auth/refresh`, {
          method: "POST",
          credentials: "include",
        });
        const refreshData = await refreshResp.json().catch(() => null);
        if (!refreshResp.ok || !refreshData?.access) {
          if (!cancelled) setOk(false);
          return;
        }
        // Refresh exitoso: guardar el nuevo access y validar con /me.
        setAccessToken(refreshData.access);
        const me = await api.get<{ id: string }>("/auth/me");
        if (!cancelled) setOk(Boolean(me));
      } catch {
        if (!cancelled) setOk(false);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  if (checking) {
    return <Splash />;
  }
  if (!ok) return <Navigate to="/login" replace />;
  return <Outlet />;
}

/**
 * Escucha global de sesión expirada (A11): cuando el refresh falla hace un
 * logout limpio (access en memoria + caché de react-query) y navega al login.
 */
function SessionExpiryHandler() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const handleSessionExpired = useCallback(() => {
    setAccessToken(null);
    queryClient.clear();
    navigate("/login", { replace: true });
  }, [navigate, queryClient]);

  useEffect(() => onSessionExpired(handleSessionExpired), [handleSessionExpired]);

  return (
    <Suspense fallback={<Splash />}>
      <Outlet />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <SessionExpiryHandler />,
    children: [
      {
        path: "/login",
        element: <LoginPage />,
      },
      {
        path: "/register",
        element: <RegisterPage />,
      },
      {
        path: "/verify",
        element: <VerifyPage />,
      },
      {
        path: "/forgot-password",
        element: <ForgotPasswordPage />,
      },
      {
        path: "/reset-password",
        element: <ResetPasswordPage />,
      },
      {
        element: <RequireAuth />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: "/", element: <DashboardPage /> },
              { path: "/wallets", element: <WalletsPage /> },
              { path: "/transactions", element: <TransactionsPage /> },
              { path: "/savings", element: <SavingsPage /> },
              { path: "/subscriptions", element: <SubscriptionsPage /> },
              { path: "/profile", element: <ProfilePage /> },
            ],
          },
          { path: "/operations/new", element: <NewOperationPage /> },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
