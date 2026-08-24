/**
 * sw-push.js — Handlers de Web Push para el service worker de NaviCash.
 *
 * El SW principal lo genera vite-plugin-pwa (workbox) y este archivo se
 * adjunta vía `workbox.importScripts` en vite.config.ts, porque generateSW
 * no permite añadir listeners directamente. Debe ser JS plano y sin build.
 * (No se lintea con reglas TS: eslint aplica a los .ts/.tsx de src.)
 */

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "NaviCash";
  event.waitUntil(
    self.registration.showNotification(title, {
      body: data.body || "",
      icon: "/icon-192x192.png",
      badge: "/icon-192x192.png",
      tag: data.kind || undefined,
      renotify: false,
      data: { url: data.url || "/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL(
    (event.notification.data && event.notification.data.url) || "/",
    self.location.origin
  ).href;
  event.waitUntil(
    (async () => {
      const clientList = await self.clients.matchAll({
        type: "window",
        includeUncontrolled: true,
      });
      // Si ya hay una ventana en la URL objetivo, enfócala; si hay cualquier
      // ventana de la app, navega la primera y enfócala.
      for (const client of clientList) {
        if (client.url === target && "focus" in client) return client.focus();
      }
      for (const client of clientList) {
        if ("focus" in client) {
          await client.focus();
          if ("navigate" in client) return client.navigate(target);
          return undefined;
        }
      }
      return self.clients.openWindow(target);
    })()
  );
});
