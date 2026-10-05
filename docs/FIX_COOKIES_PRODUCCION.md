# Fix: Cookies no viajaban en producción (Render)

> ## ACTUALIZADO: este fix cross-site era INSUFICIENTE (y es lo que rompe hoy)
>
> **Síntoma real:** la sesión moría a los ~15 minutos en todos los navegadores
> (Chrome de escritorio y Safari/iOS por igual), con este log en la API:
>
> ```
> REFRESH_REJECTED reason=no_cookie user=- ip=...
> ```
>
> **Causa raíz:** `onrender.com` está en la **Public Suffix List**, así que
> `navicash-web.onrender.com` y `navicash-api-xxxxx.onrender.com` son **sitios
> distintos**, no solo orígenes distintos. La cookie httpOnly del refresh es
> entonces **third-party**, y Chrome 1xx / Safari-iOS ya no guardan cookies
> third-party sin `Partitioned`. El login "funcionaba" (el access token viene en
> el body y CORS responde bien), pero el navegador **descartaba el
> `Set-Cookie`** en silencio: no había cookie que renovar.
>
> Poner `SameSite=None` y `CORS_ALLOWED_ORIGINS` es **necesario pero no
> suficiente**: ninguna cabecera puede forzar al navegador a guardar una cookie
> third-party.
>
> **Fix definitivo: mismo origen.** nginx hace proxy de `/api` al servicio de la
> API (`apps/web/nginx.conf`), de modo que la SPA se llama a sí misma y la
> cookie es **first-party**. Requisitos:
>
> - Web desplegado como **Web Service (Docker)** con `apps/web/Dockerfile.prod`
>   (no como Static Site: nginx no está ahí y no hay proxy).
> - `VITE_API_URL=/api` en el servicio web.
> - `CORS_ALLOWED_ORIGINS` en la API **incluyendo el origen del web** (el
>   refresh sigue validando Origin; si falta, verás `reason=origin`).
> - `JWT_COOKIE_SAMESITE=Lax` en la API (ya no hace falta `None`).
>
> Ojo al hacer el proxy a un host HTTPS: hacen falta
> `proxy_ssl_server_name on` y `proxy_ssl_protocols TLSv1.2 TLSv1.3`, o el
> handshake falla con `alert 40` y el proxy devuelve 502 en todo `/api`
> (y `nginx -t` no lo detecta).
>
> Ver el paso a paso completo en `docs/RENDER_CONFIG.md`.

## Diagnóstico del problema original

```
Error en producción (Render):
- GET /api/auth/me → 401 "Las credenciales de autenticación no se proveyeron"
- POST /api/auth/refresh → 401 "No hay sesión refrescable"

Razón: La cookie de refresh NO se estaba enviando desde el navegador
```

## Causa raíz

En producción, el frontend y backend están en **dominios separados** (Render asigna IPs diferentes):

```
Frontend: https://navicash-web-xxxxx.onrender.com  
Backend:  https://navicash-api-xxxxx.onrender.com  
```

Cuando el navegador hace una petición cross-site (POST desde web → api), la cookie HTTP solo viaja si:

1. ✅ Tiene `credentials: "include"` → **YA ESTABA** en api.ts
2. ✅ Tiene `Secure=True` (HTTPS) → **YA ESTABA** en DEBUG=False
3. ✅ Tiene `SameSite=None` → **FALTABA** (estaba en `Lax`)
4. ✅ El backend permite CORS → **FALTABA** (CORS_ALLOWED_ORIGINS vacío)

## Fix aplicado

### 1. Backend: SameSite dinámico (settings.py)

```python
# ANTES
"AUTH_COOKIE_SAMESITE": "Lax",

# AHORA  
"AUTH_COOKIE_SAMESITE": "None" if not DEBUG else "Lax",
```

**Efecto:** En producción (DEBUG=False) usa `SameSite=None` (permite cross-site); en desarrollo sigue siendo `Lax` (same-site local).

### 2. Manual: Configurar CORS en Render Dashboard

**CRÍTICO:** Después de desplegar, DEBES configurar en el dashboard:

```
CORS_ALLOWED_ORIGINS = ["https://navicash-web-xxxxx.onrender.com"]
```

Sin esto, Django rechaza la petición incluso con la cookie presente.

## Flujo ahora (producción)

```
1. Usuario hace login
   → POST /api/auth/login
   → Backend devuelve access token + cookie (SameSite=None, Secure=True)
   
2. Frontend guarda access en memoria, cookie en navegador (automático)

3. Usuario recarga la página
   → GET /api/auth/me (con Cookie: refresh_token=...)
   ✅ Funciona: la cookie viaja por CORS + SameSite=None
   
4. Si el access expira, el frontend refresa
   → POST /api/auth/refresh (con Cookie: refresh_token=...)
   ✅ Funciona: obtiene nuevo access
```

## ¿Qué debes hacer?

### En Render Dashboard (navicash-api):
1. Environment → CORS_ALLOWED_ORIGINS
   ```
   ["https://navicash-web-xxxxx.onrender.com"]
   ```

2. Environment → APP_BASE_URL (si no está)
   ```
   https://navicash-web-xxxxx.onrender.com
   ```

3. Environment → DJANGO_SECRET_KEY (si no está)
   ```
   (nueva clave: python -c "import secrets; print(secrets.token_urlsafe(64))")
   ```

4. Guardar → Auto-redeploy

### En Render Dashboard (navicash-web):
1. Environment → VITE_API_URL (si no está)
   ```
   https://navicash-api-xxxxx.onrender.com/api
   ```

2. Guardar → Auto-redeploy

## Verificación local

Todos los tests de sesión pasan:
- ✅ test_refresh_rotates_access_token
- ✅ test_refresh_rejects_reused_token  
- ✅ test_refresh_blacklists_rotated_token
- ✅ test_logout_revokes_whole_family

**38 tests pasan sin regresiones**

## Notas de seguridad

- `SameSite=None` requiere HTTPS (✓ Render fuerza TLS)
- La cookie es httpOnly (no accesible a JS, protege de XSS)
- CORS está validado al nivel de Django (no es un header blindly echo)
- El refresh es rotado y blacklisted (AUDIT C3)
