import { useCallback, useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import {
  getNaviTourView,
  isNaviTourComplete,
  isNaviTourSeen,
  markNaviTourSeen,
} from "@/features/assistant/navi-tour-content";

/**
 * Estado del tour guiado de Navi para la ruta actual.
 *
 * - Avanza paso a paso (Siguiente) y se da por "vista" al terminar u omitir.
 * - El "visto" por ruta se persiste en localStorage (preferencia de UI).
 * - Cuando todas las vistas del checklist están vistas, marca `is_onboarded`
 *   en el backend (una sola vez).
 */
export function useNaviTour(pathname: string) {
  const queryClient = useQueryClient();
  const [stepIndex, setStepIndex] = useState(0);
  const view = getNaviTourView(pathname);

  // Al cambiar de vista el tour vuelve al primer paso.
  useEffect(() => {
    setStepIndex(0);
  }, [pathname]);

  const complete = useCallback(() => {
    if (!view || isNaviTourSeen(view.pathKey)) return;
    markNaviTourSeen(view.pathKey);
    setStepIndex(0);
    if (view.checklist && isNaviTourComplete()) {
      void api
        .patch("/auth/me", { is_onboarded: true })
        .then(() => queryClient.invalidateQueries({ queryKey: queryKeys.me }))
        .catch(() => {
          // El tour ya se vio; si el PATCH falla se reintenta la próxima vista.
        });
    }
  }, [view, queryClient]);

  const next = useCallback(() => {
    if (!view) return;
    if (stepIndex >= view.stepCount - 1) {
      complete();
    } else {
      setStepIndex((i) => i + 1);
    }
  }, [view, stepIndex, complete]);

  const skip = useCallback(() => complete(), [complete]);

  const visible = view !== null && !isNaviTourSeen(view.pathKey) && stepIndex < view.stepCount;

  return {
    view,
    stepIndex,
    totalSteps: view?.stepCount ?? 0,
    visible,
    next,
    skip,
  };
}
