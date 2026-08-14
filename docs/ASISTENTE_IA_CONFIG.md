# Configurar el Asistente IA (Navi) en Render

## Opciones de proveedores soportados

El backend soporta tres proveedores de IA:

### 1. **OpenAI** (Recomendado para producción)
- Modelo: `gpt-4o-mini` (default, muy barato)
- Costo: ~$0.15 por 1M tokens input, $0.60 por 1M tokens output
- Velocidad: Rápido

### 2. **Azure OpenAI**
- Compatible con el endpoint de OpenAI
- Mejor para empresas con infraestructura Microsoft

### 3. **OpenRouter**
- Interfaz unificada para múltiples modelos (Claude, Gemini, etc.)
- Flexibilidad de cambiar modelos

### 4. **Mock** (Actual - desarrollo)
- Sin costo
- Respuestas simuladas basadas en reglas
- Perfecto para desarrollo/pruebas

---

## Pasos para configurar en Render

### Paso 1: Obtener credenciales

**Para OpenAI:**
1. Ve a https://platform.openai.com/api-keys
2. Crea una nueva API key (o usa una existente)
3. Copia la clave (formato: `sk-...`)

**Para Azure OpenAI o OpenRouter:**
- Sigue la documentación de cada proveedor

### Paso 2: Configurar en Render Dashboard

1. **Ve a tu servicio `navicash-api` en Render**
2. **Haz clic en Environment**
3. **Agrega las siguientes variables de entorno:**

```
AAI_PROVIDER = openai
AAI_API_KEY = sk-xxxxxxxxxxxxxxxxxxxxx
AAI_MODEL = gpt-4o-mini
```

### Paso 3: Variables opcionales

Si usas un endpoint diferente al de OpenAI (p. ej., Azure u OpenRouter):

```
AAI_BASE_URL = https://tu-endpoint.openai.azure.com/openai/deployments/tu-modelo/chat/completions
```

O para OpenRouter:
```
AAI_PROVIDER = openrouter
AAI_API_KEY = sk-or-xxxxxxxxxxxxxxxxxxxxx
AAI_BASE_URL = https://openrouter.ai/api/v1
```

### Paso 4: Guardar y desplegar

1. **Haz clic en Save changes**
2. Render redesplegará automáticamente el servicio
3. Los logs mostrarán: `AAI_PROVIDER = openai → usando OpenAIProvider`

---

## Verificación

Después de configurar:

1. **Abre la app**
2. **Haz clic en el ícono de Navi (burbuja de chat)**
3. **Pregunta algo** (p. ej., "¿Cuál es mi saldo?")
4. **Navi responderá usando la IA real**

En los logs del servidor (Render) verás:
```
INFO apps.assistant.providers AAI_PROVIDER = openai → usando OpenAIProvider
```

---

## Estimado de costos (OpenAI)

Asumiendo 100 usuarios activos / mes, 2 mensajes por usuario en promedio:

- **200 llamadas al API**
- **~5K tokens promedio por llamada**
- **~1M tokens/mes**
- **Costo: ~$0.15/mes**

Prácticamente gratis.

---

## Fallback automático

Si `AAI_API_KEY` está vacío o la llamada al API falla:
- ✅ Automáticamente cae a `MockAssistantProvider`
- ✅ Navi sigue funcionando con respuestas deterministas
- ✅ Sin romper la app

---

## Variables de entorno resumen

| Variable | Requerida | Default | Ejemplo |
|----------|-----------|---------|---------|
| `AAI_PROVIDER` | No | (vacío = mock) | `openai` |
| `AAI_API_KEY` | Sí (si usas IA real) | (vacío) | `sk-...` |
| `AAI_MODEL` | No | `gpt-4o-mini` | `gpt-4o` |
| `AAI_BASE_URL` | No | `https://api.openai.com/v1` | (URL customizada) |

---

## Troubleshooting

### Log: "AAI_PROVIDER sin configurar → usando MockAssistantProvider"
**Problema:** `AAI_PROVIDER` no está configurada
**Solución:** Agrega `AAI_PROVIDER = openai` en Render Environment

### Navi responde lentamente
**Problema:** Timeout de 25 segundos o respuesta del API lenta
**Solución:** Configura un modelo más rápido (p. ej., `gpt-3.5-turbo`) o revisa tu conexión

### Error: "Invalid API key"
**Problema:** La clave es inválida o está expirada
**Solución:** Regenera la clave en el dashboard de OpenAI y actualiza en Render

---

## Próximas mejoras (Fase 2)

- [ ] Caché de respuestas frecuentes
- [ ] Logs de interacción con Navi (para auditoría)
- [ ] Soporte para Anthropic Claude
- [ ] Voice input/output mejorado
