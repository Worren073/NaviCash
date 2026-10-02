import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { Outlet, useLocation, useNavigate } from "react-router-dom";

export type NavView = "personal" | "business";

const STORAGE_KEY = "navcash:view";
// Rutas que pertenecen exclusivamente a una vista: al entrar por URL directa
// la vista activa se corrige sola. El resto (transactions, profile,
// operations/new) es compartido y conserva la vista actual.
const BUSINESS_PATHS = ["/business"];
const PERSONAL_PATHS = ["/", "/wallets", "/savings", "/subscriptions", "/checklists"];

interface NavViewContextValue {
  view: NavView;
  changeView: (view: NavView) => void;
}

const NavViewContext = createContext<NavViewContextValue>({
  view: "personal",
  changeView: () => undefined,
});

export function useNavView() {
  return useContext(NavViewContext);
}

/**
 * Estado global de la vista (Personales ⇄ Negocio) para la navegación.
 *
 * - Persiste en localStorage la última vista elegida.
 * - ``changeView`` además navega al "inicio" de la vista para que el cambio
 *   nunca choque con la corrección por ruta.
 */
export function NavViewProvider() {
  const navigate = useNavigate();
  const location = useLocation();
  const [view, setView] = useState<NavView>(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === "business" ? "business" : "personal";
    } catch {
      return "personal";
    }
  });

  // Corrección por ruta: si entro directo a /business se fuerza la vista de
  // negocio; las rutas estrictamente personales fuerzan la personal.
  useEffect(() => {
    const path = location.pathname;
    let next: NavView | null = null;
    if (BUSINESS_PATHS.some((p) => path === p || path.startsWith(`${p}/`))) {
      next = "business";
    } else if (PERSONAL_PATHS.some((p) => path === p)) {
      next = "personal";
    }
    if (next && next !== view) {
      setView(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* almacenamiento no disponible: la vista vive igual en memoria */
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const changeView = useCallback(
    (next: NavView) => {
      setView(next);
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        /* idem */
      }
      navigate(next === "business" ? "/business" : "/");
    },
    [navigate]
  );

  const value = useMemo(() => ({ view, changeView }), [view, changeView]);

  return (
    <NavViewContext.Provider value={value}>
      <Outlet />
    </NavViewContext.Provider>
  );
}