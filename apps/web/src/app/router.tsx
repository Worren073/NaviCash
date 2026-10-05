import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { Navigate, Outlet, createBrowserRouter, useNavigate } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import AppLayout from "@/app/layout";
import { NavViewProvider } from "@/features/navigation/nav-view";
import { api, getAccessToken, onSessionExpired, refreshSession, setAccessToken } from "@/lib/api";
import { Splash } from "@/components/ui/blur-loading";
import { queryKeys } from "@/hooks/use-queries";
import type { User } from "@/lib/types";

// M10 — code splitting: cada página se carga bajo demanda.
const DashboardPage = lazy(() => import("@/features/dashboard/dashboard-page"));
const WalletsPage = lazy(() => import("@/features/wallets/wallets-page"));
const NewOperationPage = lazy(() => import("@/features/transactions/new-operation-page"));
const TransactionsPage = lazy(() => import("@/features/transactions/transactions-page"));
const SavingsPage = lazy(() => import("@/features/savings/savings-page"));
const SubscriptionsPage = lazy(() => import("@/features/subscriptions/subscriptions-page"));
const ChecklistsPage = lazy(() => import("@/features/checklists/checklists-page"));
const ProfilePage = lazy(() => import("@/features/profile/profile-page"));
const BusinessPage = lazy(() => import("@/features/business/business-page"));
const BusinessContactsPage = lazy(() => import("@/features/business/business-contacts-page"));
const InvoicesPage = lazy(() => import("@/features/business/invoices-page"));
const InvoiceNewPage = lazy(() => import("@/features/business/invoice-new-page"));
const InvoiceDetailPage = lazy(() => import("@/features/business/invoice-detail-page"));
const InventoryPage = lazy(() => import("@/features/business/inventory-page"));
const CollectionPage = lazy(() => import("@/features/business/collection-page"));
const LoginPage = lazy(() => import("@/features/auth/login-page"));
const RegisterPage = lazy(() => import("@/features/auth/register-page"));
const VerifyPage = lazy(() => import("@/features/auth/verify-page"));
const ForgotPasswordPage = lazy(() => import("@/features/auth/forgot-password-page"));
const ResetPasswordPage = lazy(() => import("@/features/auth/reset-password-page"));

/** Intentos de arranque antes de admitir que no hay sesión. */
const BOOTSTRAP_ATTEMPTS = 3;
/** Espera entre intentos cuando el refresh falló por red, no por rechazo. */
const BOOTSTRAP_RETRY_DELAY_MS = 1_500;

/**
 * Guard de sesión: comprueba si hay una sesión válida (access en memoria o
 * refresh cookie httpOnly) antes de mostrar las rutas privadas.
 *
 * Si no hay access en memoria, intenta refrescar usando la cookie. Si funciona,
 * hace GET /api/auth/me para validar. Si el SERVIDOR rechaza la cookie no hay
 * sesión; si solo falló la red, reintenta un par de veces antes de rendirse
 * (móvil: PWA reanudada del segundo plano o túnel sin cobertura).
 */
function RequireAuth() {
  const [checking, setChecking] = useState(() => !getAccessToken());
  const [ok, setOk] = useState(() => Boolean(getAccessToken()));
  const queryClient = useQueryClient();

useEffect(() => {
    if (getAccessToken()) return;
    let cancelled = false;
    (async () => {
      try {
        // Sin access en memoria: intentar refrescar usando la cookie.
        // Se usa el MISMO single-flight que el cliente HTTP (refreshSession):
        // nunca dos refrescos simultáneos con la misma cookie (rotación).
        for (let attempt = 1; attempt <= BOOTSTRAP_ATTEMPTS; attempt += 1) {
          if (cancelled) return;
          const outcome = await refreshSession();
          if (cancelled) return;

          if (outcome === "ok") {
            // Access ya guardado por refreshSession: validar con /me.
            const me = await api.get<User>("/auth/me");
            // Pre-cargar el perfil para que el layout (y el tour de Navi) lo lean
            // de react-query sin una petición extra.
            queryClient.setQueryData(queryKeys.me, me);
            if (!cancelled) setOk(Boolean(me));
            return;
          }

          // El servidor rechazó la cookie: no hay sesión, ir al login.
          if (outcome === "rejected") {
            if (!cancelled) setOk(false);
            return;
          }

          // Sin conexión: la sesión puede estar viva. En móvil (PWA reanudada
          // del segundo plano, túnel sin cobertura) landing aquí no significa
          // sesión caducada, así que se reintenta antes de rendirse.
          await new Promise((r) => setTimeout(r, BOOTSTRAP_RETRY_DELAY_MS));
        }
        if (!cancelled) setOk(false);
      } catch {
        if (!cancelled) setOk(false);
      } finally {
        if (!cancelled) setChecking(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [queryClient]);

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
          // La vista activa (Personales ⇄ Negocio) vive en este providers y
          // alimenta layout, menú y datos por scope de las rutas compartidas.
          {
            element: <NavViewProvider />,
            children: [
              {
                element: <AppLayout />,
                children: [
                  { path: "/", element: <DashboardPage /> },
                  { path: "/wallets", element: <WalletsPage /> },
                  { path: "/transactions", element: <TransactionsPage /> },
                  { path: "/savings", element: <SavingsPage /> },
                  { path: "/subscriptions", element: <SubscriptionsPage /> },
                  { path: "/checklists", element: <ChecklistsPage /> },
                  { path: "/profile", element: <ProfilePage /> },
                  { path: "/business", element: <BusinessPage /> },
                  { path: "/business/contacts", element: <BusinessContactsPage /> },
                  { path: "/business/invoices", element: <InvoicesPage /> },
                  { path: "/business/invoices/new", element: <InvoiceNewPage /> },
                  { path: "/business/invoices/:id", element: <InvoiceDetailPage /> },
                  { path: "/business/inventory", element: <InventoryPage /> },
                  { path: "/business/collection", element: <CollectionPage /> },
                ],
              },
              { path: "/operations/new", element: <NewOperationPage /> },
            ],
          },
        ],
      },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
]);
