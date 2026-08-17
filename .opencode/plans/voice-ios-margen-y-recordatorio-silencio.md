# Margen superior (X detrás del reloj iOS) + recordatorio de modo silencio

## Contexto

- El form de registrar pago/cobro (`new-operation-page.tsx`) es un overlay
  `fixed inset-0` cuyo header usa `px-5 py-4` sin `env(safe-area-inset-top)`:
  en iPhone la X queda detrás del reloj/Dynamic Island.
- El overlay de voz (`navi-voice.tsx`) tiene el mismo problema: su botón X es
  `absolute right-5 top-5`, también sin safe-area.
- El `main` del layout (`app/layout.tsx`) sí respeta el safe-area
  (`pt-[calc(env(safe-area-inset-top)+3.5rem)]`), por eso el dashboard se ve bien.

## Decisiones (confirmadas por el usuario)

1. Arreglar el margen superior en AMBOS: form de registrar operación y X del
   overlay de voz.
2. Recordatorio del botón de silencio: SIEMPRE visible en iOS (línea discreta
   con icono bajo el estado de la bolita).

## Cambios

### 1. `apps/web/src/features/transactions/new-operation-page.tsx`

Header (aprox. línea 140): `px-5 py-4` → `px-5 pt-[calc(env(safe-area-inset-top)+1rem)] pb-4`
(en desktop/Android el safe-area es 0 → sin cambio visual).

### 2. `apps/web/src/features/assistant/navi-voice.tsx`

- Botón X (aprox. línea 226): `absolute right-5 top-5` →
  `absolute right-5 top-[calc(env(safe-area-inset-top)+1.25rem)]`.
- Importar `VolumeX` de `lucide-react` y `isIOSDevice` de `@/hooks/use-device-os`.
- `const ios = isIOSDevice();`
- Añadir (solo si `ios`) una línea con `VolumeX` + texto `t("assistant.voice.silentMode")`,
  en el pie del overlay, entre la sección de estado y el aviso legal.

### 3. i18n

- `apps/web/src/i18n/es.ts` (objeto `assistant.voice`):
  `silentMode: "Si el botón de silencio está activado, no escucharás la voz de Navi.",`
- `apps/web/src/i18n/en.ts` (objeto `assistant.voice`):
  `silentMode: "If silent mode is on, you won't hear Navi's voice.",`

## Verificación

- `npm run typecheck`, `npm run lint`, `npm run build` (con `VITE_CAPTCHA_SITE_KEY`
  dummy, requerida por vite.config.ts para builds de producción).
- Prueba manual en iPhone: form de registrar operación (X despejada del reloj),
  overlay de voz (X despejada + recordatorio visible), Navi hablando.

## Fuera de alcance

- TTS del lado servidor (alternativa si speechSynthesis de iOS no bastara).
- No hay cambios de backend.
