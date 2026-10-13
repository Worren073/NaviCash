import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { InvoiceDetail } from "./invoice-detail";

export default function InvoiceDetailPage() {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();

  if (!id) return null;

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link
        to="/business/invoices"
        className="mb-3 inline-flex items-center gap-1 text-sm text-primary transition-opacity hover:opacity-80"
      >
        <ArrowLeft className="h-4 w-4" /> {t("invoices.detail.back")}
      </Link>
      <InvoiceDetail id={id} />
    </div>
  );
}
