import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Mail,
  MapPin,
  Pencil,
  Phone,
  Plus,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { sileo } from "sileo";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDeleteDialog } from "@/components/ui/confirm-delete-dialog";
import { Segmented } from "@/components/ui/segmented";
import { useBusinessContacts } from "@/hooks/use-queries";
import { queryKeys } from "@/hooks/use-queries";
import { api, ApiErrorClass } from "@/lib/api";
import type { BusinessContact, Currency } from "@/lib/types";

const TYPE_OPTIONS = [
  { value: "", label: "contacts.types.all" },
  { value: "cliente", label: "contacts.types.cliente" },
  { value: "proveedor", label: "contacts.types.proveedor" },
  { value: "ambos", label: "contacts.types.ambos" },
];

const CUSTOMER_TYPES = [
  { value: "", label: "contacts.customerTypes.none" },
  { value: "minorista", label: "contacts.customerTypes.minorista" },
  { value: "mayorista", label: "contacts.customerTypes.mayorista" },
];

const CURRENCIES: Currency[] = ["USD", "VES"];

function emptyForm() {
  return {
    name: "",
    email: "",
    phone: "",
    address: "",
    tax_id: "",
    type: "cliente" as BusinessContact["type"],
    customer_type: "" as BusinessContact["customer_type"],
    payment_terms_days: 0,
    credit_limit: "",
    currency: "USD" as Currency,
    notes: "",
    is_active: true,
  };
}

function ContactForm({
  value,
  onChange,
}: {
  value: ReturnType<typeof emptyForm>;
  onChange: (next: ReturnType<typeof emptyForm>) => void;
}) {
  const { t } = useTranslation();
  const update = <K extends keyof typeof value>(key: K, val: (typeof value)[K]) =>
    onChange({ ...value, [key]: val });

  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.name")}
        </span>
        <Input
          value={value.name}
          onChange={(e) => update("name", e.target.value)}
          placeholder={t("contacts.namePlaceholder")}
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.type")}
        </span>
        <select
          value={value.type}
          onChange={(e) =>
            update("type", e.target.value as BusinessContact["type"])
          }
          className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
        >
          {TYPE_OPTIONS.slice(1).map((opt) => (
            <option key={opt.value} value={opt.value}>
              {t(opt.label)}
            </option>
          ))}
        </select>
      </label>

      {value.type !== "proveedor" && (
        <label className="block">
          <span className="mb-1 block text-sm font-medium text-on-surface">
            {t("contacts.customerType")}
          </span>
          <select
            value={value.customer_type}
            onChange={(e) =>
              update("customer_type", e.target.value as BusinessContact["customer_type"])
            }
            className="h-11 w-full rounded-xl border border-glass-border bg-glass-surface px-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
          >
            {CUSTOMER_TYPES.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {t(opt.label)}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.email")}
        </span>
        <Input
          type="email"
          value={value.email}
          onChange={(e) => update("email", e.target.value)}
          placeholder={t("contacts.emailPlaceholder")}
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.phone")}
        </span>
        <Input
          value={value.phone}
          onChange={(e) => update("phone", e.target.value)}
          placeholder={t("contacts.phonePlaceholder")}
        />
      </label>

      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.address")}
        </span>
        <Input
          value={value.address}
          onChange={(e) => update("address", e.target.value)}
          placeholder={t("contacts.addressPlaceholder")}
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.taxId")}
        </span>
        <Input
          value={value.tax_id}
          onChange={(e) => update("tax_id", e.target.value)}
          placeholder={t("contacts.taxIdPlaceholder")}
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.paymentTerms")}
        </span>
        <Input
          type="number"
          min={0}
          value={value.payment_terms_days}
          onChange={(e) =>
            update("payment_terms_days", Number(e.target.value))
          }
        />
      </label>

      <label className="block">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.creditLimit")}
        </span>
        <div className="flex items-center gap-2">
          <select
            value={value.currency}
            onChange={(e) => update("currency", e.target.value as Currency)}
            className="h-11 rounded-xl border border-glass-border bg-glass-surface px-2 text-sm text-on-surface outline-none"
          >
            {CURRENCIES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
          <Input
            type="number"
            min="0"
            step="0.01"
            value={value.credit_limit}
            onChange={(e) => update("credit_limit", e.target.value)}
            placeholder="0.00"
            className="flex-1"
          />
        </div>
      </label>

      <label className="block sm:col-span-2">
        <span className="mb-1 block text-sm font-medium text-on-surface">
          {t("contacts.notes")}
        </span>
        <textarea
          value={value.notes}
          onChange={(e) => update("notes", e.target.value)}
          placeholder={t("contacts.notesPlaceholder")}
          rows={3}
          className="w-full rounded-xl border border-glass-border bg-glass-surface p-3 text-base text-on-surface shadow-sm outline-none backdrop-blur-md focus-visible:border-primary focus-visible:ring-2 focus-visible:ring-primary/30 md:text-sm"
        />
      </label>
    </div>
  );
}

function ContactCard({
  contact,
  onEdit,
  onDelete,
}: {
  contact: BusinessContact;
  onEdit: (c: BusinessContact) => void;
  onDelete: (c: BusinessContact) => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="glass-panel clip-rounded-lg flex items-start justify-between gap-3 rounded-lg p-4">
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-on-surface">{contact.name}</span>
          <Badge variant="secondary">{t(`contacts.types.${contact.type}`)}</Badge>
          {contact.customer_type && (
            <Badge variant="outline">
              {t(`contacts.customerTypes.${contact.customer_type}`)}
            </Badge>
          )}
          {!contact.is_active && (
            <Badge variant="outline" className="text-on-surface-variant">
              {t("contacts.inactive")}
            </Badge>
          )}
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-on-surface-variant">
          {contact.phone && (
            <span className="flex items-center gap-1">
              <Phone className="h-3.5 w-3.5" /> {contact.phone}
            </span>
          )}
          {contact.email && (
            <span className="flex items-center gap-1">
              <Mail className="h-3.5 w-3.5" /> {contact.email}
            </span>
          )}
          {contact.address && (
            <span className="flex items-center gap-1">
              <MapPin className="h-3.5 w-3.5" /> {contact.address}
            </span>
          )}
        </div>
        <div className="text-xs text-on-surface-variant">
          {contact.tax_id && (
            <span className="mr-3">{t("contacts.taxId")}: {contact.tax_id}</span>
          )}
          <span>
            {t("contacts.paymentTerms")}: {contact.payment_terms_days} {t("contacts.days")}
          </span>
          {contact.credit_limit && (
            <span className="ml-3">
              {t("contacts.creditLimit")}: {contact.credit_limit} {contact.currency}
            </span>
          )}
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8"
          onClick={() => onEdit(contact)}
          aria-label={t("common.edit")}
        >
          <Pencil className="h-4 w-4" />
        </Button>
        <Button
          size="icon"
          variant="ghost"
          className="h-8 w-8 text-error"
          onClick={() => onDelete(contact)}
          aria-label={t("common.delete")}
        >
          <Trash2 className="h-4 w-4" />
        </Button>
      </div>
    </div>
  );
}

export default function BusinessContactsPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<BusinessContact | null>(null);
  const [form, setForm] = useState(emptyForm());
  const [deleteContact, setDeleteContact] = useState<BusinessContact | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const { data, isLoading, isError } = useBusinessContacts(
    debouncedSearch || undefined,
    typeFilter || undefined
  );

  const contacts = useMemo(() => data?.results ?? [], [data]);

  const save = useMutation({
    mutationFn: () => {
      const payload = {
        ...form,
        credit_limit: form.credit_limit === "" ? null : form.credit_limit,
      };
      if (editing) {
        return api.patch<BusinessContact>(`/business/contacts/${editing.id}/`, payload);
      }
      return api.post<BusinessContact>("/business/contacts/", payload);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.businessContacts });
      setDialogOpen(false);
      setEditing(null);
      setForm(emptyForm());
      sileo.success({ title: t(editing ? "contacts.updated" : "contacts.created") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const remove = useMutation({
    mutationFn: () =>
      api.delete(`/business/contacts/${deleteContact!.id}/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.businessContacts });
      setDeleteContact(null);
      sileo.success({ title: t("contacts.deleted") });
    },
    onError: (err) => {
      const msg = err instanceof ApiErrorClass ? err.message : t("errors.generic");
      sileo.error({ title: msg });
    },
  });

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm());
    setDialogOpen(true);
  };

  const openEdit = (contact: BusinessContact) => {
    setEditing(contact);
    setForm({
      name: contact.name,
      email: contact.email,
      phone: contact.phone,
      address: contact.address,
      tax_id: contact.tax_id,
      type: contact.type,
      customer_type: contact.customer_type,
      payment_terms_days: contact.payment_terms_days,
      credit_limit: contact.credit_limit ?? "",
      currency: contact.currency,
      notes: contact.notes,
      is_active: contact.is_active,
    });
    setDialogOpen(true);
  };

  const canSave = form.name.trim().length > 0;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <Users className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-on-surface">{t("contacts.title")}</h1>
            <p className="text-sm text-on-surface-variant">{t("contacts.subtitle")}</p>
          </div>
        </div>
        <Button variant="glow" onClick={openCreate} className="gap-1">
          <Plus className="h-4 w-4" /> {t("contacts.add")}
        </Button>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("contacts.searchPlaceholder")}
            className="pl-9"
          />
        </div>
        <Segmented
          layoutId="seg-contact-type"
          size="sm"
          options={TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
          value={typeFilter}
          onChange={setTypeFilter}
        />
      </div>

      {isError ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-6 text-center text-sm text-on-surface-variant">
          {t("errors.generic")}
        </p>
      ) : isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : contacts.length === 0 ? (
        <p className="glass-panel clip-rounded-lg rounded-lg p-8 text-center text-sm text-on-surface-variant">
          {t("contacts.empty")}
        </p>
      ) : (
        <div className="space-y-2">
          {contacts.map((c) => (
            <ContactCard
              key={c.id}
              contact={c}
              onEdit={openEdit}
              onDelete={setDeleteContact}
            />
          ))}
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>
              {t(editing ? "contacts.editTitle" : "contacts.createTitle")}
            </DialogTitle>
            <DialogDescription>{t("contacts.formHint")}</DialogDescription>
          </DialogHeader>
          <ContactForm value={form} onChange={setForm} />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setDialogOpen(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              variant="glow"
              onClick={() => save.mutate()}
              disabled={!canSave || save.isPending}
            >
              {save.isPending ? t("common.loading") : t("common.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <ConfirmDeleteDialog
        open={Boolean(deleteContact)}
        onOpenChange={(open) => !open && setDeleteContact(null)}
        itemName={t("contacts.contact")}
        itemLabel={deleteContact?.name}
        onConfirm={() => remove.mutate()}
        pending={remove.isPending}
      />
    </div>
  );
}
