import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import es from "./es";
import en from "./en";

export const resources = {
  es: { translation: es },
  en: { translation: en },
} as const;

export const defaultNS = "translation";

/** M9 — detección por navegador, sin dependencias: solo "en" gana, resto es. */
function detectLanguage(): string {
  if (typeof navigator !== "undefined" && navigator.language?.toLowerCase().startsWith("en")) {
    return "en";
  }
  return "es";
}

i18n.use(initReactI18next).init({
  resources,
  lng: detectLanguage(),
  fallbackLng: "es",
  defaultNS,
  returnNull: false,
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;