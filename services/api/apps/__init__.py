"""apps — Paquete que agrupa los módulos de dominio del backend.

Cada subpaquete es una app Django de negocio:

+----------------+------------------------------------------------------+
| App            | Responsabilidad                                      |
+----------------+------------------------------------------------------+
| core           | Utilidades transversales (dinero, modelos base, etc.)|
| accounts       | Usuarios, registro, verificación de email y JWT      |
| rates          | Tasas de cambio (DolarApi), caché e histórico        |
| wallets        | Billeteras y saldos                                   |
| transactions   | Cobros/pagos, estados, categorías y contactos         |
| savings        | Metas de ahorro y aportes                             |
| shortcuts      | Atajos del home                                       |
| overview       | Endpoints de resumen del dashboard                    |
+----------------+------------------------------------------------------+
"""