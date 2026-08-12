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
**Valor requerido:**
```
https://navicash-api-xxxxx.onrender.com/api
```
(URL de tu API en Render)

**Por qué:** Le dice al frontend dónde llamar al backend.

---

## Pasos para aplicar:

1. Ve al dashboard de Render
2. Selecciona el servicio **navicash-api**
3. Haz clic en **Environment**
4. Edita/agrega cada variable de arriba
5. Haz clic en **Save changes**
6. El servicio se redeployará automáticamente
7. Repite para el servicio **navicash-web** si necesitas cambiar VITE_API_URL

---

## ¿Por qué la cookie no viajaba?

La cookie de refresh tiene `SameSite=Lax` (en desarrollo) y `SameSite=None` (en producción).

- **En desarrollo (localhost):** Same-site, funciona con Lax.
- **En producción (dos dominios distintos en Render):** Cross-site, requiere `SameSite=None + Secure=True + CORS`.

El fix automático en `settings.py` ya aplica `SameSite=None` cuando `DEBUG=False` (producción).

Para que funcione, DEBES:
1. ✅ Configurar `CORS_ALLOWED_ORIGINS` con la URL del frontend
2. ✅ El backend está en HTTPS (Render maneja TLS automáticamente)
3. ✅ Las cookies tienen `Secure=True` en producción (configurado)

Sin el paso 1, el navegador rechaza la cookie antes de que Django la procese.
