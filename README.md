# CodeMio Backend

<div align="center">

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.2.11-092E20?style=for-the-badge&logo=django&logoColor=white)
![DRF](https://img.shields.io/badge/DRF-3.15.2-ff1709?style=for-the-badge&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-316192?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Latest-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![Gunicorn](https://img.shields.io/badge/Gunicorn-22.0.0-499848?style=for-the-badge&logo=gunicorn&logoColor=white)

</div>

---

## 📋 Descripción

**CodeMio Backend** es una API REST desarrollada con Django que permite realizar análisis estático de código fuente Java para obtener métricas de calidad del software.

### ¿Qué hace este sistema?

El proyecto consiste en el desarrollo de una aplicación web que permita a los usuarios:

- **Subir código Java:** Carga de archivos `.java` individuales o proyectos completos comprimidos en formato `.zip`
- **Análisis automático:** El backend procesa los archivos con **PMD** y **SpotBugs** para detectar hallazgos de calidad y buenas prácticas
- **Dashboard de métricas:** Generación de dashboard por proyecto mostrando los resultados del análisis
- **Evaluación de calidad:** Las métricas son evaluadas contra rangos definidos para determinar si cumplen buenas prácticas o representan posibles problemas de diseño
- **Gestión de proyectos:** Sistema completo de CRUD para proyectos y archivos

### Características Principales

✅ **Registro y autenticación de usuarios** con **Amazon Cognito** (OTP por correo, registro, login JWT, renovación con refresh token, logout, **recuperación de contraseña en tres pasos** con sondeo de OTP) y perfil local (`Usuario`); ver [authentication/README.md](authentication/README.md)  
✅ **Gestión completa de proyectos Java** (crear, editar, eliminar, listar)  
✅ **Carga de archivos** individuales o en lote (`.java` y `.zip`)  
✅ **Descompresión automática** de archivos comprimidos  
✅ **Procesamiento asíncrono** para análisis de código  
✅ **Persistencia de archivos y métricas** en base de datos  
✅ **API REST completa** para integración con frontend  
✅ **Administración avanzada** para supervisores

> **Nota:** El sistema **no modifica ni corrige** el código; únicamente lo analiza y presenta resultados.

---

## 🛠️ Stack Tecnológico

| Categoría | Tecnología | Versión | Propósito |
|-----------|-----------|---------|-----------|
| **Framework** | Django | 5.2.11 | Framework web principal |
| **API** | Django REST Framework | 3.15.2 | Construcción de API REST |
| **Base de Datos** | PostgreSQL | 16+ | Persistencia de datos |
| **Servidor WSGI** | Gunicorn | 22.0.0 | Servidor de producción |
| **Análisis de Código** | PMD + SpotBugs | CLI tools | Análisis estático de Java |
| **Contenedores** | Docker | Latest | Contenedorización |
| **CI/CD** | GitHub Actions | - | Integración continua |
| **Despliegue** | Render | - | Hosting y despliegue |
| **CORS** | django-cors-headers | 4.4.0 | Manejo de CORS |
| **Variables de Entorno** | python-decouple | 3.8 | Configuración |

---

## 📚 Documentación Adicional

Este proyecto incluye documentación detallada para facilitar el desarrollo:

| Archivo | Propósito |
|---------|-----------|
| [`README.md`](README.md) | **Guía principal** - Instalación, configuración y uso general |
| [`authentication/README.md`](authentication/README.md) | **Autenticación** - Flujo Cognito (send → validate → register → login → refresh → users/me → logout), **forgot-password → validate-code → confirm-forgot-password**, tokens y modelos |
| [`CONFIGURATION_SUMMARY.md`](CONFIGURATION_SUMMARY.md) | **Resumen de configuración** - Explicación detallada de todos los archivos de configuración |
| [`COMMANDS.md`](COMMANDS.md) | **Referencia de comandos** - Lista completa de comandos útiles para desarrollo |
| [`PROJECT_MAP.md`](PROJECT_MAP.md) | **Mapa técnico del proyecto** - Arquitectura y flujos visualizados con Mermaid |
| [`setup.sh`](setup.sh) | **Script de configuración** - Automatización de setup del entorno de desarrollo |

---

## 📦 Requisitos Previos

- Python 3.12+
- PostgreSQL (para producción)
- Docker (opcional, para contenedorización)
- Git

---

### Método 1: Script Automatizado (Recomendado)

```bash
# Clonar el repositorio
git clone <repository-url>
cd codemio_back

# Ejecutar script de configuración
chmod +x setup.sh
./setup.sh

# Iniciar servidor
source venv/bin/activate
python manage.py runserver
```

El script `setup.sh` automáticamente:
- ✅ Crea el entorno virtual
- ✅ Instala todas las dependencias
- ✅ Genera el archivo `.env` con SECRET_KEY
- ✅ Ejecuta las migraciones

### Método 2: Configuración Manual

Sigue los pasos detallados a continuación.

---

## 🚀 Instalación y Configuración Local

### 1. Clonar el repositorio

```bash
git clone <repository-url>
cd codemio_back
```

### 2. Crear y activar entorno virtual

**Linux/macOS:**
```bash
python -m venv venv
source venv/bin/activate
```

**Windows:**
```bash
python -m venv venv
venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

Crea un archivo `.env` en la raíz del proyecto basándote en `.env.example`:

```bash
cp .env.example .env
```

Edita el archivo `.env` con tus configuraciones:

```env
SECRET_KEY=tu-secret-key-generada
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Para desarrollo local con SQLite (por defecto)
# DATABASE_URL no es necesario

# Para desarrollo con PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/codemio_db

# Análisis estático (valores portables via PATH)
ANALYSIS_PMD_COMMAND=pmd
ANALYSIS_SPOTBUGS_COMMAND=spotbugs
ANALYSIS_JAVAC_COMMAND=javac
```

Si tu entorno no resuelve esos comandos por `PATH`, define rutas absolutas solo en tu `.env` local
(por ejemplo `/opt/homebrew/bin/pmd`), sin subir rutas específicas de sistema al repositorio.

**Generar SECRET_KEY:**
```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Ejecutar migraciones

```bash
python manage.py migrate
```

### 6. Crear superusuario (opcional)

```bash
python manage.py createsuperuser
```

### 7. Ejecutar servidor de desarrollo

```bash
python manage.py runserver
```

El servidor estará disponible en: `http://localhost:8000`

> 💡 **Tip:** Para más comandos útiles, consulta [`COMMANDS.md`](COMMANDS.md)

---

### Construir imagen Docker

```bash
docker build -t codemio-backend .
```

### Ejecutar contenedor

```bash
docker run -p 8000:8000 \
  -e SECRET_KEY="your-secret-key" \
  -e DEBUG=False \
  -e DATABASE_URL="postgresql://user:password@host:5432/database" \
  -e ALLOWED_HOSTS=".render.com,localhost" \
  codemio-backend
```

### Docker Compose (opcional)

Puedes crear un `docker-compose.yml` para desarrollo local:

```yaml
version: '3.8'

services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: codemio_db
      POSTGRES_USER: codemio_user
      POSTGRES_PASSWORD: codemio_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://codemio_user:codemio_password@db:5432/codemio_db
      - DEBUG=True
    depends_on:
      - db

volumes:
  postgres_data:
```

Ya existe un `docker-compose.yml` configurado. Simplemente ejecuta:

```bash
docker-compose up
```

Para detener:

```bash
docker-compose down
```

> 📖 **Más información:** Consulta [`CONFIGURATION_SUMMARY.md`](CONFIGURATION_SUMMARY.md#-archivos-docker) para detalles sobre la configuración de Docker.

---

### Instalar nueva dependencia

```bash
pip install nombre-paquete
pip freeze > requirements.txt
```

### Actualizar dependencias

```bash
pip install --upgrade -r requirements.txt
pip freeze > requirements.txt
```

### Desactivar entorno virtual

```bash
deactivate
```

> 💡 **Más comandos:** Ver [`COMMANDS.md`](COMMANDS.md#-entorno-virtual) para gestión completa de dependencias.

---

```
codemio_back/
├── codemio_back/          # Configuración principal del proyecto
│   ├── __init__.py
│   ├── asgi.py
│   ├── settings.py        # Configuración de Django
│   ├── urls.py            # URLs principales
│   └── wsgi.py            # WSGI para producción
├── .github/
│   └── workflows/
│       └── ci.yml         # GitHub Actions CI/CD
├── manage.py              # Comando principal de Django
├── requirements.txt       # Dependencias Python
├── Dockerfile             # Configuración Docker
├── .dockerignore          # Archivos excluidos de Docker
├── .gitignore             # Archivos excluidos de Git
├── .env.example           # Plantilla de variables de entorno
└── README.md              # Este archivo
```

> 📐 **Arquitectura completa:** Ver [`PROJECT_MAP.md`](PROJECT_MAP.md) para diagramas de arquitectura y flujos.

---

### Configuración

1. Conecta tu repositorio de GitHub con Render
2. Crea un nuevo **Web Service**
3. Configura las siguientes variables de entorno en Render:

```
SECRET_KEY=<generar-nueva-clave>
DEBUG=False
ALLOWED_HOSTS=.render.com
DATABASE_URL=<proporcionado-por-render-postgresql>
CORS_ALLOWED_ORIGINS=https://tu-frontend.render.com
PORT=8000
```

4. Render detectará automáticamente el `Dockerfile` y lo usará para el despliegue

### Base de Datos

1. Crea una **PostgreSQL Database** en Render
2. Copia la **Internal Database URL**
3. Pégala como valor de `DATABASE_URL` en las variables de entorno del Web Service

### Despliegue Automático

Cada push a la rama `main` activará:
1. GitHub Actions ejecutará tests y validará el build de Docker
2. Render detectará el commit y construirá/desplegará automáticamente

> 📋 **Guía detallada:** Para instrucciones paso a paso de despliegue, consulta la [documentación oficial de Render](https://render.com/docs/deploy-django).

---

```bash
# Ejecutar todos los tests
python manage.py test

# Ejecutar tests de una app específica
python manage.py test app_name

# Con cobertura
pip install coverage
coverage run --source='.' manage.py test
coverage report
```

> 🧪 **Testing avanzado:** Ver [`COMMANDS.md`](COMMANDS.md#-testing) para más opciones de testing.

---

- Nunca commitees el archivo `.env`
- Usa `SECRET_KEY` diferentes para desarrollo y producción
- Mantén `DEBUG=False` en producción
- Actualiza dependencias regularmente
- Revisa las alertas de seguridad de GitHub

## 📝 Conventional Commits

Este proyecto sigue [Conventional Commits v1.0.0](https://www.conventionalcommits.org/):

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

**Tipos permitidos:**
- `feat`: Nueva funcionalidad
- `fix`: Corrección de errores
- `docs`: Cambios en documentación
- `style`: Cambios de formato (no afectan lógica)
- `refactor`: Refactorización de código
- `perf`: Mejoras de rendimiento
- `test`: Agregar o modificar tests
- `build`: Cambios en sistema de construcción
- `ci`: Cambios en CI/CD
- `chore`: Tareas auxiliares

**Ejemplos:**
```bash
git commit -m "feat: add user authentication endpoint"
git commit -m "fix: resolve database connection issue"
git commit -m "docs: update installation instructions"
```

## 🤝 Contribución

1. Fork el proyecto
2. Crea una rama para tu feature (`git checkout -b feat/amazing-feature`)
3. Commit tus cambios siguiendo Conventional Commits
4. Push a la rama (`git push origin feat/amazing-feature`)
5. Abre un Pull Request usando el [template de PR](.github/pull_request_template.md)

### 📝 Templates Disponibles

El proyecto incluye templates de GitHub para facilitar la colaboración:

| Template | Uso |
|----------|-----|
| **[Pull Request](.github/pull_request_template.md)** | Se aplica automáticamente al crear un PR |
| **[Task](.github/ISSUE_TEMPLATE/task.yml)** | Crear nuevas tareas de desarrollo |
| **[Bug Report](.github/ISSUE_TEMPLATE/bug_report.yml)** | Reportar errores o problemas |
| **[Feature Request](.github/ISSUE_TEMPLATE/feature_request.yml)** | Proponer nuevas funcionalidades |

> 💡 **Tip:** Los templates de issues aparecerán automáticamente al crear un nuevo issue en GitHub.

---

## 👥 Equipo

Desarrollado por el equipo de CodeMio - UTEZ

### Integrantes del Proyecto

<table>
  <tr>
    <th>Nombre</th>
    <th>Rol(es)</th>
    <th>GitHub</th>
  </tr>
  <tr>
    <td><strong>Miguel Angel Sanchez Perez</strong></td>
    <td>
      🔐 Administrador de Bases de Datos y Seguridad<br/>
      🧪 Lead de Integración y QA
    </td>
    <td>
      <a href="https://github.com/MiguelSP040">
        <img src="https://img.shields.io/badge/GitHub-MiguelSP040-181717?style=flat-square&logo=github" alt="MiguelSP040"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><strong>Martin Antonio Joaquín Landa</strong></td>
    <td>⚙️ Desarrollador Backend</td>
    <td>
      <a href="https://github.com/M4ltin12">
        <img src="https://img.shields.io/badge/GitHub-M4ltin12-181717?style=flat-square&logo=github" alt="M4ltin12"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><strong>Daniela Carrate Bahena</strong></td>
    <td>🎨 Frontend & UX</td>
    <td>
      <a href="https://github.com/danielita05">
        <img src="https://img.shields.io/badge/GitHub-danielita05-181717?style=flat-square&logo=github" alt="danielita05"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><strong>Luis David Rojas Vargas</strong></td>
    <td>💻 Desarrollador JS</td>
    <td>
      <a href="https://github.com/DavidReds7">
        <img src="https://img.shields.io/badge/GitHub-DavidReds7-181717?style=flat-square&logo=github" alt="DavidReds7"/>
      </a>
    </td>
  </tr>
  <tr>
    <td><strong>Luis Ignacio Valera Aguilar</strong></td>
    <td>📊 Business Intelligence</td>
    <td>
      <a href="https://github.com/IgnacioValera">
        <img src="https://img.shields.io/badge/GitHub-IgnacioValera-181717?style=flat-square&logo=github" alt="IgnacioValera"/>
      </a>
    </td>
  </tr>
</table>

### Contacto del Equipo

Para consultas específicas del proyecto, puedes contactar a los integrantes a través de sus perfiles de GitHub o crear un issue en el repositorio.

---

Para reportar problemas o solicitar características, abre un issue en el repositorio.
