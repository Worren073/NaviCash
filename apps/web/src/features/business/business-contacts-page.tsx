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
import {
  TAX_ID_TYPES,
  formatTaxId,
  taxIdHintKey,
  taxIdNumberPlaceholder,
  type TaxIdType,
} from "@/lib/tax-id";
import type { BusinessContact } from "@/lib/types";
import {
  ContactForm,
  emptyContactForm,
  type ContactFormValue,
} from "./contact-form";

const TYPE_OPTIONS = [
  { value: "", label: "contacts.types.all" },
  { value: "cliente", label: "contacts.types.cliente" },
  { value: "proveedor", label: "contacts.types.proveedor" },
  { value: "ambos", label: "contacts.types.ambos" },
];

/** Opciones del filtro por tipo de cédula: "Todos" + V/J/E. */
const TAX_TYPE_OPTIONS = [
  { value: "", label: "contacts.types.all" },
  ...TAX_ID_TYPES.map((value) => ({ value, label: value })),
];

/**
 * Compone el término de búsqueda con el filtro de tipo de cédula.
 *
 * - Sin tipo seleccionado: texto libre (nombre, correo, teléfono o cédula).
 * - Con tipo y campo vacío: no se manda ``search``; el filtro ``tax_id_type``
 *   del backend se encarga de listar solo ese tipo.
 * - Con tipo y dígitos: cédula canónica ("J" + "1234" -> "J-1234").
 */
function buildSearchTerm(raw: string, taxType: TaxIdType | ""): string {
  const text = raw.trim();
  if (!taxType) return text;
  if (!text) return "";
  // Se reutiliza el saneador para que E conserve lo alfanumérico ("A123" ->
  // "E-A123") y para tolerar guiones ya escritos ("310-12345" -> "J-31012345").
  const number = sanitizeTaxNumber(text, taxType);
  return number ? formatTaxId(taxType, number) : "";
}

/** Limpia lo que se escribe según el tipo: solo dígitos, salvo E (alfanumérico). */
function sanitizeTaxNumber(raw: string, taxType: TaxIdType): string {
  const cleaned = raw.toUpperCase().replace(/[\s._-]/g, "");
  return taxType === "E" ? cleaned.replace(/[^A-Z0-9]/g, "") : cleaned.replace(/\D/g, "");
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
          <span className="mr-3">
            {contact.tax_id
              ? `${t("contacts.taxId")}: ${contact.tax_id}`
              : t("contacts.noTaxId")}
          </span>
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
  const [taxType, setTaxType] = useState<TaxIdType | "">("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState<BusinessContact | null>(null);
  const [form, setForm] = useState<ContactFormValue>(emptyContactForm());
  const [deleteContact, setDeleteContact] = useState<BusinessContact | null>(null);

  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search), 300);
    return () => clearTimeout(id);
  }, [search]);

  const searchTerm = buildSearchTerm(debouncedSearch, taxType);
  const hasFilters =
    searchTerm.length > 0 || typeFilter.length > 0 || taxType.length > 0;

  const { data, isLoading, isError } = useBusinessContacts(
    searchTerm || undefined,
    typeFilter || undefined,
    taxType || undefined
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
      setForm(emptyContactForm());
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
    setForm(emptyContactForm());
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

      <div className="space-y-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-on-surface-variant" />
          <Input
            value={search}
            onChange={(e) => {
              const next = e.target.value;
              setSearch(taxType ? sanitizeTaxNumber(next, taxType) : next);
            }}
            inputMode={taxType ? (taxType === "E" ? "text" : "numeric") : "search"}
            placeholder={
              taxType
                ? taxIdNumberPlaceholder(taxType)
                : t("contacts.searchPlaceholder")
            }
            aria-label={taxType ? t(taxIdHintKey(taxType)) : t("contacts.searchPlaceholder")}
            className="pl-9"
          />
        </div>

        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-on-surface-variant">
              {t("contacts.taxId")}
            </span>
            <Segmented
              layoutId="seg-contact-tax-type"
              size="sm"
              options={TAX_TYPE_OPTIONS.map((o) => ({
                value: o.value,
                label: t(o.label),
              }))}
              value={taxType}
              onChange={(next) => {
                const value = next as TaxIdType | "";
                setTaxType(value);
                // Se re-limpia para el nuevo tipo: lo alfanumérico de E se
                // descarta al pasar a V/J para no dejar una búsqueda imposible.
                setSearch(value && search ? sanitizeTaxNumber(search, value) : "");
              }}
            />
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-on-surface-variant">
              {t("contacts.type")}
            </span>
            <Segmented
              layoutId="seg-contact-type"
              size="sm"
              options={TYPE_OPTIONS.map((o) => ({ value: o.value, label: t(o.label) }))}
              value={typeFilter}
              onChange={setTypeFilter}
            />
          </div>
        </div>

        {taxType && (
          <p className="text-xs text-on-surface-variant">{t(taxIdHintKey(taxType))}</p>
        )}
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
          {hasFilters ? t("contacts.emptyFiltered") : t("contacts.empty")}
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
