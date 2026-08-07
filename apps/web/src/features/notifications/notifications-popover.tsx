import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { BellRing, CalendarClock, Check, Info, Target } from "lucide-react";

import { useNotifications, queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { GlassPopover } from "@/components/ui/glass-popover";
import type { NotificationItem } from "@/lib/types";

const KIND_ICON: Record<NotificationItem["kind"], typeof Info> = {
  due_soon: CalendarClock,
  overdue: BellRing,
  goal_reached: Target,
  system: Info,
};

function NotificationRow({ item }: { item: NotificationItem }) {
  const Icon = KIND_ICON[item.kind] ?? Info;
  return (
    <div
      className={`flex gap-3 rounded-xl px-3 py-2 ${
        item.read ? "" : "bg-surface-container-high/40"
      }`}
    >
      <div
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full ${
          item.read ? "bg-surface-container-high" : "bg-primary/15"
        }`}
      >
        <Icon className={`h-4 w-4 ${item.read ? "text-on-surface-variant" : "text-primary"}`} />
      </div>
      <div className="min-w-0 flex-1">
        <p
          className={`text-sm leading-snug ${
            item.read ? "text-on-surface-variant" : "font-medium text-on-surface"
          }`}
        >
          {item.title}
        </p>
        <p className="mt-0.5 text-xs leading-snug text-on-surface-variant">{item.message}</p>
      </div>
    </div>
  );
}

export function NotificationsPopover({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data, isLoading } = useNotifications();

  const markAll = useMutation({
    mutationFn: () => api.post<{ detail: string }>("/notifications/read-all"),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.notifications });
    },
    onError: (err) => {
      if (err instanceof ApiErrorClass) void err;
    },
  });

  const items = data?.results ?? [];
  const unread = data?.unread_count ?? 0;

  return (
    <GlassPopover
      open={open}
      onClose={onClose}
      className="w-[22rem] bg-white/90 backdrop-blur-[60px]"
    >
      <div className="flex items-center justify-between border-b border-glass-border px-4 py-3">
        <span className="text-sm font-semibold text-on-surface">{t("notifications.title")}</span>
        {unread > 0 && (
          <Button
            size="sm"
            variant="ghost"
            className="h-7 px-2 text-xs"
            onClick={() => markAll.mutate()}
            disabled={markAll.isPending}
          >
            <Check className="h-3.5 w-3.5" /> {t("notifications.markAll")}
          </Button>
        )}
      </div>
      <div className="max-h-80 overflow-y-auto px-2 py-2">
        {isLoading ? (
          <p className="px-3 py-8 text-center text-sm text-on-surface-variant">
            {t("common.loading")}
          </p>
        ) : items.length === 0 ? (
          <p className="px-3 py-8 text-center text-sm text-on-surface-variant">
            {t("notifications.empty")}
          </p>
        ) : (
          items.slice(0, 12).map((item) => <NotificationRow key={item.id} item={item} />)
        )}
      </div>
    </GlassPopover>
  );
}