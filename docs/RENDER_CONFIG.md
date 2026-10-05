# Configuración manual en Render Dashboard

## Variables de entorno CRÍTICAS (requieren ser seteadas en el dashboard)

Después de desplegar, accede al dashboard de Render y configura EXACTAMENTE estas variables en el servicio **navicash-api**:

### 1. CORS_ALLOWED_ORIGINS
**Valor requerido:**
```
["https://navicash-web-xxxxx.onrender.com"]
```
Reemplaza `xxxxx` con el ID real de tu servicio web en Render (está en la URL del frontend en Render).

**Por qué:** Sin esto, las cookies httpOnly no viajarán desde el frontend. El backend rechazará la petición con un error CORS.

### 2. APP_BASE_URL
**Valor requerido:**
```
https://navicash-web-xxxxx.onrender.com
```
(Mismo ID que arriba)

**Por qué:** Se usa para construir enlaces de verificación de email y recuperación de contraseña.

### 3. DJANGO_SECRET_KEY
**Valor requerido:** Una clave aleatoria y única, p. ej.:
```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

**Por qué:** SimpleJWT y las sesiones Django la usan para firmar los tokens. NUNCA uses la de desarrollo.

### 4. TURNSTILE_SECRET_KEY
**Valor requerido:** Tu clave secreta de Cloudflare Turnstile (si aplica).

**Por qué:** Validación de CAPTCHA en el registro.

### 5. BREVO_API_KEY
**Valor requerido:** Tu clave de API de Brevo (para envío de emails en producción).

**Por qué:** Sin esto los correos de verificación no se enviarán.

### 6. VITE_API_URL (en el servicio frontend)
**Valor requerido (mismo origen, nginx hace proxy de `/api`):**
```
/api
```
**NO** la URL absoluta de la API: con la API en otro subdominio de
`*.onrender.com` la cookie del refresh es third-party y el navegador no la
guarda (ver `FIX_COOKIES_PRODUCCION.md`). Con `/api`, nginx reenvía la petición
y la cookie queda first-party.

**Por qué:** Le dice al frontend dónde llamar al backend.

### 7. JWT_COOKIE_SAMESITE (en navicash-api)
**Valor recomendado:** `Lax`

Es el `SameSite` de la cookie httpOnly del refresh. Con la API en el mismo
origen la cookie es first-party y `Lax` es más estricto que `None` (un POST
cross-site ni siquiera lleva la cookie). Déjalo en `None` solo si despliegas la
SPA en otro dominio.

---

## El frontend debe ser Web Service (Docker), NO Static Site

Con un Static Site no hay nginx y por tanto **no hay proxy**: la SPA acaba
hablando cross-site con la API y la cookie del refresh no sobrevive.

Configuración del servicio web:

| Campo | Valor |
|---|---|
| Type | Web Service |
| Runtime | Docker |
| Root Directory | `apps/web` |
| Dockerfile Path | `./Dockerfile.prod` |
| Docker Context | `.` |
| `VITE_API_URL` | `/api` |
| `VITE_CAPTCHA_SITE_KEY` | la de tu cuenta de Turnstile |

`Dockerfile.prod` declara `ARG VITE_API_URL` y `ARG VITE_CAPTCHA_SITE_KEY`: sin
esos `ARG` las variables no llegan al build de Docker y `vite.config.ts` aborta
con *"VITE_CAPTCHA_SITE_KEY es obligatoria para build de producción"*.

Al crear este servicio **cambia la URL del frontend**: Render no permite
convertir un Static Site en Web Service. Avisa el origen nuevo en
`CORS_ALLOWED_ORIGINS` y en `APP_BASE_URL` de la API antes de probarlo, porque
el refresh valida Origin.

---

## Pasos para aplicar:

1. Ve al dashboard de Render
2. Selecciona el servicio **navicash-api**
3. Haz clic en **Environment**
4. Edita/agrega cada variable de arriba
5. Haz clic en **Save changes**
6. El servicio se redeployará automáticamente
7. Crea (o actualiza) el servicio **navicash-web** como Web Service con la tabla
   de arriba y `VITE_API_URL=/api`
8. Con la URL nueva que te asigne Render, agrégala a `CORS_ALLOWED_ORIGINS` y
   `APP_BASE_URL` de la API y redeploy de la API
9. Prueba en el móvil: login y navega a Negocio pasado el expiry del access
   token (15 min). Para no esperar, baja `JWT_ACCESS_MINUTES` a 2, prueba y
   déjalo en 15
10. Cuando esté todo bien, borra el Static Site viejo y la PWA instalada en el
    teléfono (se instala de nuevo desde la URL nueva)

---

## ¿Por qué la cookie no viajaba?

Porque en `*.onrender.com` la SPA y la API son **sitios distintos** (el dominio
está en la Public Suffix List), no solo orígenes distintos. La cookie de
refresh viaja como **third-party** y Chrome 1xx / Safari-iOS no la guardan sin
`Partitioned`: el navegador descarta el `Set-Cookie` del login en silencio.

Ninguna cabecera HTTP lo arregla: `SameSite=None`, `Secure` y CORS correcto
siguen sin ser suficientes. La cookie solo sobrevive si es **first-party**, y
para eso la API tiene que servirse en el mismo origen (proxy de nginx).

Cómo reconocerlo: `REFRESH_REJECTED reason=no_cookie` en el log de la API, y la
sesión muriendo ~15 minutos después de entrar.
