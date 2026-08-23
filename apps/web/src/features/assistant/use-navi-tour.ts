import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import {
  NAVI_TOUR_RESET_EVENT,
  getNaviTourView,
  getSeenTourViews,
  isNaviTourComplete,
  markNaviTourSeen,
} from "@/features/assistant/navi-tour-content";

/**
 * Estado del tour guiado de Navi para la ruta actual.
 *
 * - Avanza paso a paso (Siguiente) y se da por "vista" al terminar u omitir.
 * - El "visto" por ruta se persiste en localStorage (preferencia de UI), pero
 *   se ESPEJA en estado: `visible` debe reaccionar a Omitir/cerrar aunque el
 *   paso no cambie (un setState con el mismo valor no provoca re-render).
 * - Cuando todas las vistas del checklist están vistas, marca `is_onboarded`
 *   en el backend (una sola vez).
 */
export function useNaviTour(pathname: string) {
  const queryClient = useQueryClient();
  const [stepIndex, setStepIndex] = useState(0);
  const [seenViews, setSeenViews] = useState<string[]>(getSeenTourViews);
  const view = getNaviTourView(pathname);

  // Al cambiar de vista el tour vuelve al primer paso.
  useEffect(() => {
    setStepIndex(0);
  }, [pathname]);

  // "Ver tutorial de nuevo" limpia localStorage fuera del hook: re-sincroniza.
  useEffect(() => {
    const sync = () => setSeenViews(getSeenTourViews());
    window.addEventListener(NAVI_TOUR_RESET_EVENT, sync);
    return () => window.removeEventListener(NAVI_TOUR_RESET_EVENT, sync);
  }, []);

  const complete = useCallback(() => {
    if (!view || seenViews.includes(view.pathKey)) return;
    markNaviTourSeen(view.pathKey);
    // Array nuevo siempre → re-render garantizado aunque stepIndex ya sea 0.
    setSeenViews((prev) =>
      prev.includes(view.pathKey) ? prev : [...prev, view.pathKey],
    );
    setStepIndex(0);
    if (view.checklist && isNaviTourComplete()) {
      void api
        .patch("/auth/me", { is_onboarded: true })
        .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.me }))
        .catch(() => {
          // El tour ya se vio; si el PATCH falla se reintenta la próxima vista.
        });
    }
  }, [view, seenViews, queryClient]);

  const next = useCallback(() => {
    if (!view) return;
    if (stepIndex >= view.stepCount - 1) {
      complete();
    } else {
      setStepIndex((i) => i + 1);
    }
  }, [view, stepIndex, complete]);

  const skip = useCallback(() => complete(), [complete]);

  const visible = view !== null && !seenViews.includes(view.pathKey) && stepIndex < view.stepCount;

  return {
    view,
    stepIndex,
    totalSteps: view?.stepCount ?? 0,
    visible,
    next,
    skip,
  };
}
