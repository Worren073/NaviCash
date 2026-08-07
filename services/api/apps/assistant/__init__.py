"""apps — App del asistente conversacional "Navi".

Fase 1 del plan `docs/AI-ASSISTANT.md`: el backend construye un contexto
agregado del dominio del usuario, decide la respuesta con un proveedor de LLM
desacoplado y cae a reglas deterministas si el proveedor falla.
"""