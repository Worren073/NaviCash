import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import es from "./es";

export const resources = {
  es: { translation: es },
} as const;

export const defaultNS = "translation";

i18n.use(initReactI18next).init({
  resources,
  lng: "es",
  fallbackLng: "es",
  defaultNS,
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;