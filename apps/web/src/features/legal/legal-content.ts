export interface LegalDoc {
  title: string;
  body: string;
}

export const TERMS_CONTENT: LegalDoc = {
  title: "Términos y Condiciones de Uso",
  body: `## 1. Aceptación de los Términos

Al crear una cuenta en NaviCash, aceptas estos Términos y Condiciones y nuestra Política de Privacidad. Si no estás de acuerdo, no uses el servicio.

## 2. Descripción del Servicio

NaviCash es una aplicación de gestión de finanzas personales que te permite:
- Registrar ingresos, gastos y transferencias entre tus cuentas
- Gestionar metas de ahorro y suscripciones recurrentes
- Recibir recordatorios de vencimientos
- Consultar saldos y reportes
- Interactuar con Navi, un asistente conversacional que registra operaciones por voz o texto

NaviCash no es un banco, una entidad financiera ni un asesor de inversiones. No custodia fondos, no realiza movimientos de dinero real y no ofrece asesoría financiera, legal ni tributaria.

## 3. Cuenta de Usuario

- Debes ser mayor de 18 años (o la mayoría de edad en tu jurisdicción)
- Eres responsable de mantener confidenciales tu email y tu contraseña
- Debes notificarnos inmediatamente cualquier uso no autorizado de tu cuenta
- Nos reservamos el derecho de suspender o eliminar cuentas que incumplan estos Términos

## 4. Uso Permitido y Prohibido

Uso permitido: uso personal, legal y legítimo para organizar tus finanzas.

Uso prohibido:
- Uso para actividades fraudulentas, lavado de dinero o ilegales
- Ingeniería inversa, extracción de datos o acceso no autorizado a la API
- Compartir credenciales o permitir el acceso a terceros
- Interferir con la seguridad o la estabilidad del servicio

## 5. Datos y Privacidad

El tratamiento de tus datos se rige por nuestra Política de Privacidad. En resumen:
- Tus datos financieros son tuyos y no los vendemos
- Solo accedemos a ellos para prestarte el servicio
- Puedes solicitar la eliminación de tu cuenta y tus datos en cualquier momento

## 6. Asistente Navi

Navi es un asistente basado en modelos de lenguaje, con un modo de respaldo determinista.
- Puede cometer errores: verifica siempre la información importante
- No es un asesor financiero: sus respuestas son orientativas
- Las operaciones que sugiere requieren tu confirmación explícita
- NaviCash no se responsabiliza por las decisiones que tomes basándote en sus respuestas

## 7. Tasas de Cambio

Las tasas del Banco Central de Venezuela (BCV) se obtienen de fuentes públicas y se guardan en caché.
- Son referenciales y pueden diferir del mercado real
- NaviCash no garantiza su exactitud ni su disponibilidad continua

## 8. Disponibilidad y Cambios

- El servicio se ofrece tal cual, sin garantía de disponibilidad ininterrumpida
- Podemos introducir mejoras, cambios o suspender el servicio con un aviso razonable
- Los cambios relevantes a estos Términos se notificarán por email

## 9. Limitación de Responsabilidad

En la máxima medida permitida por la ley:
- NaviCash no responde por errores de cálculo, por decisiones financieras basadas en la aplicación ni por daños indirectos
- La responsabilidad total se limita al monto pagado por el usuario (si aplica) en los últimos 12 meses

## 10. Ley Aplicable y Jurisdicción

Estos Términos se rigen por las leyes de la República Bolivariana de Venezuela. Cualquier disputa se resolverá ante los tribunales competentes de Caracas.

## 11. Contacto

Para dudas sobre estos Términos o sobre el tratamiento de tus datos: soporte@navicash.app`,
};

export const PRIVACY_CONTENT: LegalDoc = {
  title: "Política de Privacidad",
  body: `## 1. Responsable del Tratamiento

NaviCash es el responsable del tratamiento de tus datos personales. Puedes escribirnos en cualquier momento a soporte@navicash.app.

## 2. Qué Datos Recopilamos

Los datos que nos proporcionas directamente:
- Tu cuenta: tu correo electrónico, nombre, apellido, teléfono (opcional) y tu contraseña, guardada de forma segura.
- Tu perfil: la moneda que usas habitualmente, tu zona horaria, tu idioma y cómo quieres que te avisemos de los vencimientos.
- Tus datos financieros: cada operación que registres (monto, moneda, categoría, concepto y fecha), las cuentas o billeteras que crees, tus metas de ahorro, las suscripciones y los contactos que guardes.
- Tus conversaciones con Navi: los mensajes de chat o voz que uses para registrar operaciones con el asistente.

Los datos que generamos automáticamente:
- Tokens para verificar tu correo, recuperar tu contraseña y mantener tu sesión.
- Registros de acceso, auditoría de saldos y preferencias de notificaciones.

## 3. Para Qué Usamos Tus Datos

| Finalidad | Base Legal |
| Crear y gestionar tu cuenta | Ejecución del contrato |
| Enviar verificación y recuperación de contraseña | Interés legítimo o tu consentimiento |
| Procesar tus operaciones y generar reportes | Ejecución del contrato |
| Enviar recordatorios y notificaciones | Interés legítimo o tu consentimiento |
| Mejorar el servicio (analíticas anónimas) | Interés legítimo |
| Cumplir obligaciones legales | Obligación legal |

## 4. Con Quién Compartimos Tus Datos

No vendemos tus datos. Solo los compartimos con:
- Proveedores de infraestructura (alojamiento, email, base de datos) bajo contrato de tratamiento.
- Autoridades competentes si nos lo exige la ley.
- Servicios de inteligencia artificial para que Navi funcione, enviando solo el mensaje actual y el contexto mínimo, sin identificarte.

## 5. Transferencias Internacionales

Nuestros servidores pueden estar en Estados Unidos o en la Unión Europea. Si hay transferencia de datos, usamos cláusulas contractuales tipo u otras garantías adecuadas.

## 6. Tus Derechos

Puedes ejercerlos en cualquier momento escribiendo a soporte@navicash.app:
- Acceso: saber qué datos tenemos tuyos.
- Rectificación: corregir datos inexactos.
- Supresión: eliminar tu cuenta y tus datos (salvo que la ley nos obligue a conservarlos).
- Limitación: restringir el tratamiento.
- Portabilidad: recibir tus datos en un formato estructurado.
- Oposición: oponerte al tratamiento por interés legítimo.
- Decisiones no automatizadas: no tomamos decisiones que te afecten de forma significativa solo mediante algoritmos.

## 7. Cuánto Tiempo Guardamos Tus Datos

- Datos de cuenta: mientras la cuenta esté activa, más tres años después de eliminarla.
- Operaciones: diez años (obligación contable y fiscal).
- Registros de acceso: un año.
- Tokens de sesión: 30 días (refresh) y 15 minutos (access).

## 8. Seguridad

- Contraseñas cifradas con un algoritmo seguro, nunca en texto plano.
- Comunicaciones protegidas con HTTPS.
- Sesiones seguras con tokens de corta duración y renovación controlada.
- Verificación de que eres una persona real (CAPTCHA) en el registro e inicio de sesión.
- Límite de intentos por usuario y por dirección IP.

## 9. Menores de Edad

La aplicación no está dirigida a menores de 18 años y no recopilamos sus datos conscientemente.

## 10. Cambios en Esta Política

Te avisaremos de los cambios relevantes por email y en la aplicación. La versión actualizada quedará publicada aquí.

## 11. Contacto

Delegado de Protección de Datos: soporte@navicash.app`,
};
