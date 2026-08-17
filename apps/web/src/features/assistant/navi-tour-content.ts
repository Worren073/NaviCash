// Contenido del tour guiado de Navi: un mini-tutorial por vista para usuarios
// nuevos. Cada vista apunta a un bloque de claves i18n
// `assistant.tour.views.<pathKey>.<n>.title|body`.
//
// `checklist=true` marca las vistas que cuentan para completar el onboarding
// (marcar `User.is_onboarded`). `/operations/new` es un tour "extra" del
// formulario: se muestra una vez pero no bloquea la finalización.

export interface NaviTourView {
  path: string;
  pathKey: string;
  /** Si cuenta para completar el onboarding global. */
  checklist: boolean;
  stepCount: number;
}

export const NAVI_TOUR_VIEWS: NaviTourView[] = [
  { path: "/", pathKey: "dashboard", checklist: true, stepCount: 3 },
  { path: "/wallets", pathKey: "wallets", checklist: true, stepCount: 3 },
  { path: "/transactions", pathKey: "transactions", checklist: true, stepCount: 3 },
  { path: "/savings", pathKey: "savings", checklist: true, stepCount: 3 },
  { path: "/subscriptions", pathKey: "subscriptions", checklist: true, stepCount: 2 },
  { path: "/profile", pathKey: "profile", checklist: true, stepCount: 2 },
  { path: "/operations/new", pathKey: "newOperation", checklist: false, stepCount: 3 },
];

const STORAGE_PREFIX = "navi.tour.seen.";

export function getNaviTourView(pathname: string): NaviTourView | null {
  const clean = pathname.replace(/\/+$/, "") || "/";
  const exact = NAVI_TOUR_VIEWS.find((v) => v.path === clean);
  if (exact) return exact;
  return NAVI_TOUR_VIEWS.find((v) => v.path !== "/" && clean.startsWith(v.path)) ?? null;
}

export function isNaviTourSeen(pathKey: string): boolean {
  try {
    return window.localStorage.getItem(STORAGE_PREFIX + pathKey) === "1";
  } catch {
    return false;
  }
}

export function markNaviTourSeen(pathKey: string): void {
  try {
    window.localStorage.setItem(STORAGE_PREFIX + pathKey, "1");
  } catch {
    // localStorage no disponible: no es crítico.
  }
}

export function isNaviTourComplete(): boolean {
  return NAVI_TOUR_VIEWS.filter((v) => v.checklist).every((v) => isNaviTourSeen(v.pathKey));
}

export function resetNaviTour(): void {
  try {
    for (const v of NAVI_TOUR_VIEWS) {
      window.localStorage.removeItem(STORAGE_PREFIX + v.pathKey);
    }
  } catch {
    // localStorage no disponible: no es crítico.
  }
}
