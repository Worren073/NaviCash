import { useTranslation } from "react-i18next";

import { useBusiness } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { BusinessOnboarding } from "@/features/business/business-onboarding";
import { BusinessDashboard } from "@/features/business/business-dashboard";

export default function BusinessPage() {
  const { t } = useTranslation();
  const { data, isLoading, isError, refetch } = useBusiness();

  if (isLoading) {
    return (
      <div className="mt-6 space-y-3">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (isError) {
    return (
      <div className="glass-panel clip-rounded-lg mt-6 rounded-lg p-6 text-center">
        <p className="mb-3 text-sm text-on-surface-variant">⚠️ {t("errors.generic")}</p>
        <Button size="sm" variant="outline" onClick={() => refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }

  // Sin negocio (404) → onboarding de 3 pasos; con negocio → dashboard.
  return data ? <BusinessDashboard /> : <BusinessOnboarding />;
}