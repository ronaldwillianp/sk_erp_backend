# 🏢 ERP Ligero para Pequeños Negocios

> Sistema de gestión empresarial simplificado diseñado para pequeños negocios, freelancers y tiendas locales. Enfocado en la simplicidad extrema y la "contabilidad invisible".

## 📋 Descripción General

Este ERP permite llevar el control de un negocio sin la complejidad de sistemas empresariales tradicionales. La clave del diseño es la **automatización contable invisible**: el sistema genera los asientos y movimientos financieros en segundo plano sin que el usuario necesite conocimientos contables.

### 🎯 Filosofía de Diseño

- **Menos es más:** Interfaz minimalista, flujos cortos
- **Contabilidad invisible:** El usuario no necesita saber de "Debe" y "Haber"
- **Móvil primero:** Funcional en cualquier dispositivo
- **Exportable:** El usuario nunca pierde el control de sus datos

---

## 🛠️ Stack Tecnológico

| Capa | Tecnología |
|------|------------|
| **Backend** | Django + Django REST Framework |
| **Base de Datos** | PostgreSQL |
| **Frontend** | Vue 3 + Composition API |
| **Estado Global** | Pinia |
| **UI Framework** | Vuetify / Tailwind CSS |
| **Gráficos** | Chart.js / ApexCharts |
| **Autenticación** | JWT / Token Authentication |

---

## 📦 Módulos del Sistema

### 1️⃣ Módulo de Configuración ✅ *(Parcialmente Implementado)*

**Propósito:** Cimiento del sistema. Define la identidad del negocio y las reglas globales.

#### Modelos

| Modelo | Descripción |
|--------|-------------|
| `CompanyProfile` | Datos legales y operativos del negocio (nombre, NIT, logo, moneda) |
| `CustomUser` | Usuarios con roles (ADMIN, ACCOUNTANT, SALES) |
| `TaxRate` | Impuestos configurables (IVA general, reducido, exento) |
| `Category` | Categorías de ingresos/gastos jerárquicas |
| `PaymentMethod` | Métodos de pago (efectivo, tarjeta, transferencia) |
| `Currency` | Monedas disponibles |

#### Funcionalidades

- ✅ CRUD de empresa (singleton)
- ✅ Gestión de impuestos activos/inactivos
- ✅ Categorías con subcategorías
- ✅ Filtros por tipo (INCOME/EXPENSE)
- ✅ Permisos basados en roles (`IsAdminOrReadOnly`)
- ✅ Endpoints REST completos

#### Endpoints Disponibles

/api/v1.0/configuration/company/
/api/v1.0/configuration/tax-rates/
/api/v1.0/configuration/categories/
/api/v1.0/configuration/payment-methods/
/api/v1.0/configuration/users/


---

### 2️⃣ Módulo de Inventario 🔄 *(Pendiente)*

**Propósito:** Control de stock y catálogo de productos/servicios.

#### Modelos Propuestos

| Modelo | Descripción |
|--------|-------------|
| `Product` | Productos con precio costo/venta, SKU, stock mínimo |
| `Service` | Servicios (sin stock) o flag en Product |
| `StockMovement` | Entradas/salidas de inventario |
| `Supplier` | Proveedores básicos |

#### Funcionalidades

- CRUD de productos y servicios
- Cálculo automático de stock actual basado en movimientos
- Alertas de stock mínimo
- Historial de movimientos de inventario
- Búsqueda y filtros por categoría
- Importación masiva desde CSV

---

### 3️⃣ Módulo de Ventas (CRM Ligero) 🔄 *(Pendiente)*

**Propósito:** Gestión de clientes, cotizaciones y facturación.

#### Modelos Propuestos

| Modelo | Descripción |
|--------|-------------|
| `Customer` | Clientes con datos de contacto e historial |
| `Quote` | Cotizaciones (borrador → enviada → aceptada) |
| `Invoice` | Facturas emitidas |
| `InvoiceItem` | Líneas de factura (producto, cantidad, precio) |

#### Funcionalidades

- Conversión de cotización a factura con un clic
- Generación automática de PDF de facturas
- Cálculo automático de impuestos y totales
- Estados: `Borrador`, `Enviada`, `Pagada`, `Parcialmente Pagada`, `Vencida`, `Cancelada`
- Historial de ventas por cliente
- Búsqueda rápida de clientes
- Notas y términos en la factura

---

### 4️⃣ Módulo de Compras / Gastos 🔄 *(Pendiente)*

**Propósito:** Registro de gastos y facturas de proveedores.

#### Modelos Propuestos

| Modelo | Descripción |
|--------|-------------|
| `Expense` | Gastos simples (con foto del recibo) |
| `Bill` | Facturas de proveedores pendientes de pago |
| `BillItem` | Líneas de factura de proveedor |

#### Funcionalidades

- Registro rápido de gastos (upload de imagen del ticket)
- Clasificación automática por categoría
- Estados: `Pendiente`, `Pagado`
- Adjuntar archivos (PDF/JPG)
- Alertas de facturas por vencer
- Historial de compras por proveedor

---

### 5️⃣ Módulo de Finanzas Simplificadas 🔄 *(Pendiente)*

**Propósito:** Contabilidad automática y conciliación bancaria. **El corazón de la propuesta de valor.**

#### Modelos Propuestos

| Modelo | Descripción |
|--------|-------------|
| `Account` | Cuentas (Caja, Banco 1, Banco 2, etc.) |
| `Transaction` | Movimientos bancarios/caja |
| `Payment` | Pagos vinculados a facturas/gastos |

#### Funcionalidades Clave

**🤖 Automatización Invisible (via Django Signals):**
- Al marcar factura como pagada → crea `Transaction` automáticamente
- Al registrar gasto → crea `Transaction` automáticamente
- Actualización automática de saldos en `Account`

**Otras funcionalidades:**
- Importación de extractos bancarios (CSV)
- Conciliación automática (match entre transacciones y facturas)
- Registro manual de ingresos/egresos
- Cálculo en tiempo real de saldo por cuenta

#### Reportes Financieros

- **Flujo de Caja (Cash Flow):** ¿Cuánto dinero tengo hoy?
- **P&L Simplificado:** Ingresos - Gastos = Utilidad
- **Cuentas por Cobrar:** ¿Quién me debe?
- **Cuentas por Pagar:** ¿A quién debo?

---

### 6️⃣ Módulo de Dashboard / Reportes 🔄 *(Pendiente)*

**Propósito:** Vista rápida del estado del negocio. Responde 3 preguntas en 5 segundos.

#### Funcionalidades

- **Métricas en tiempo real:**
  - Ventas del mes vs mes anterior
  - Top 5 clientes
  - Gastos por categoría (gráfico de pastel)
  - Facturas vencidas próximas
- Exportación de datos a Excel/CSV
- Gráficos interactivos
- KPIs personalizables

---

## 🔄 Flujo de Trabajo Principal

┌─────────────┐
│  Cliente    │
└──────┬──────┘
       │
       ▼
┌─────────────┐      ┌──────────────┐
│ Cotización  │─────▶│   Factura    │
└─────────────┘      └──────┬───────┘
                            │
                            ▼
                     ┌──────────────┐
                     │   Pago       │
                     └──────┬───────┘
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
       ┌──────────┐  ┌──────────┐  ┌──────────┐
       │Transacción│  │  Stock   │  │  P&L     │
       │(Caja/Banco)│  │(Descuenta)│  │(Actualiza)│
       └──────────┘  └──────────┘  └──────────┘


---

## 📋 Próximos Pasos

### Fase 1: Completar Base ✅
- [x] Modelos de Configuración
- [x] Serializers y ViewSets
- [ ] Probar endpoints con Postman
- [ ] Frontend básico para gestión de empresa

### Fase 2: Inventario 🔄
- [ ] Modelos de productos y stock
- [ ] CRUD de productos
- [ ] Movimientos de inventario automáticos

### Fase 3: Ventas 💰
- [ ] Gestión de clientes
- [ ] Creación de facturas
- [ ] Generación de PDF
- [ ] Estados de pago

### Fase 4: Finanzas 🏦
- [ ] Cuentas bancarias
- [ ] Automatización con signals
- [ ] Conciliación bancaria
- [ ] Reportes P&L y Cash Flow

### Fase 5: Dashboard 📊
- [ ] APIs de métricas
- [ ] Gráficos en Vue
- [ ] Exportación de datos

---

## 🔐 Permisos y Roles

| Rol | Acceso |
|-----|--------|
| **ADMIN** | Control total del sistema |
| **ACCOUNTANT** | Lectura total + reportes financieros |
| **SALES** | Ventas, clientes, cotizaciones |
| **WAREHOUSE** | Inventario y movimientos de stock |

---

## 📝 Notas de Implementación

### Reglas de Oro

1. **Menos clicks es mejor:** Crear una factura debe tomar menos de 1 minuto
2. **Móvil primero:** Responsive design obligatorio
3. **Onboarding guiado:** Configuración inicial mínima (moneda, impuesto, categoría)
4. **Exportabilidad:** Siempre permitir exportar a Excel

### Evitar en MVP

- ❌ Nómina compleja (integrar con software externo)
- ❌ Manufactura avanzada (MRP)
- ❌ Multi-almacén complejo
- ❌ Contabilidad fiscal avanzada (dejar al contador)

---

## 📅 Información del Proyecto

- **Fecha de inicio:** 2026
- **Estado actual:** Fase 1 (Configuración parcial)
- **Última actualización:** 29 de julio, 2026

---

## 🤝 Contribución

Para contribuir al proyecto:
1. Revisar los módulos pendientes
2. Seguir las convenciones de Django REST Framework
3. Mantener la simplicidad como principio rector
4. Documentar cada nueva funcionalidad

---

> 💡 **Principio rector:** "Mientras otros ERPs requieren un curso de 2 días, este debe poder usarse intuitivamente en 15 minutos."