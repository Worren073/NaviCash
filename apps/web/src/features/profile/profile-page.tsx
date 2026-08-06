import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LogoutIcon, SaveIcon } from "@/components/icons";

import { api, ApiErrorClass, setAccessToken } from "@/lib/api";
import { queryKeys } from "@/hooks/use-queries";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import type { User } from "@/lib/types";

export default function ProfilePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: me } = useQuery({
    queryKey: queryKeys.me,
    queryFn: () => api.get<User>("/auth/me"),
  });

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [reminderDays, setReminderDays] = useState("3");
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const save = useMutation({
    mutationFn: () =>
      api.patch<User>("/auth/me", {
        first_name: firstName,
        last_name: lastName,
        phone,
        reminder_days: Number(reminderDays),
      }),
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: queryKeys.me });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) setError(err.message);
      else setError(t("errors.generic"));
    },
  });

  const logout = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/auth/logout"),
    onSuccess: () => {
      setAccessToken(null);
      queryClient.clear();
      navigate("/login");
    },
  });

useEffect(() => {
    if (me) {
      setFirstName(me.first_name ?? "");
      setLastName(me.last_name ?? "");
      setPhone(me.phone ?? "");
      setReminderDays(String(me.reminder_days ?? 3));
    }
  }, [me]);

  return (
    <div className="mt-4 space-y-6">
      <h2 className="text-3xl font-bold text-on-surface">{t("profile.title")}</h2>

      {!me ? (
        <Skeleton className="h-40 w-full" />
      ) : (
        <>
          <form
            className="glass-panel space-y-4 rounded-2xl p-5"
            onSubmit={(e) => {
              e.preventDefault();
              setSaved(false);
              setError(null);
              save.mutate();
            }}
          >
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label htmlFor="pfirst">{t("auth.firstName")}</Label>
                <Input
                  id="pfirst"
                  value={firstName}
                  onChange={(e) => setFirstName(e.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="plast">{t("auth.lastName")}</Label>
                <Input
                  id="plast"
                  value={lastName}
                  onChange={(e) => setLastName(e.target.value)}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pphone">{t("auth.phone")}</Label>
              <Input
                id="pphone"
                type="tel"
                placeholder="+58 424 123 4567"
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="pbase">{t("profile.baseCurrency")}</Label>
              <Input id="pbase" value={me.base_currency} readOnly />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="ptz">{t("profile.timezone")}</Label>
              <Input id="ptz" value={me.timezone_name} readOnly />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="premind">{t("profile.reminderDays")}</Label>
              <Input
                id="premind"
                type="number"
                min="0"
                max="30"
                value={reminderDays}
                onChange={(e) => setReminderDays(e.target.value)}
              />
            </div>

            {error && (
              <p className="rounded-lg bg-error-container/60 px-3 py-2 text-sm text-on-error-container">
                {error}
              </p>
            )}
            {saved && (
              <p className="rounded-lg bg-income/10 px-3 py-2 text-sm text-income">
                {t("profile.saved")}
              </p>
            )}

            <Button type="submit" className="w-full" disabled={save.isPending}>
              <SaveIcon size={16} /> {save.isPending ? t("common.loading") : t("profile.save")}
            </Button>
          </form>

          <Button
            variant="outline"
            className="w-full text-status-delayed"
            onClick={() => logout.mutate()}
            disabled={logout.isPending}
          >
            <LogoutIcon size={16} /> {logout.isPending ? t("common.loading") : t("auth.logout")}
          </Button>
        </>
      )}
    </div>
  );
}