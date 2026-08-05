import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import { useEffect, useState } from "react";

import AppLayout from "@/app/layout";
import DashboardPage from "@/features/dashboard/dashboard-page";
import WalletsPage from "@/features/wallets/wallets-page";
import NewOperationPage from "@/features/transactions/new-operation-page";
import TransactionsPage from "@/features/transactions/transactions-page";
import SavingsPage from "@/features/savings/savings-page";
import ProfilePage from "@/features/profile/profile-page";
import LoginPage from "@/features/auth/login-page";
import RegisterPage from "@/features/auth/register-page";
import VerifyPage from "@/features/auth/verify-page";
import { api, getAccessToken } from "@/lib/api";
import { Splash } from "@/components/ui/blur-loading";

/**
 * Guard de sesión: comprueba si hay una sesión válida (access en memoria o
 * refresh cookie httpOnly) antes de mostrar las rutas privadas.
 */
function RequireAuth() {
  const [checking, setChecking] = useState(() => !getAccessToken());
  const [ok, setOk] = useState(() => Boolean(getAccessToken()));

  useEffect(() => {
    if (getAccessToken()) return;
    let cancelled = false;
    (async () => {
      try {
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

export const router = createBrowserRouter([
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
    element: <RequireAuth />,
    children: [
      {
        element: <AppLayout />,
        children: [
          { path: "/", element: <DashboardPage /> },
          { path: "/wallets", element: <WalletsPage /> },
          { path: "/operations/new", element: <NewOperationPage /> },
          { path: "/transactions", element: <TransactionsPage /> },
          { path: "/savings", element: <SavingsPage /> },
          { path: "/profile", element: <ProfilePage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);