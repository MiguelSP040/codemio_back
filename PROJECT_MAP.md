# 🗺️ Mapa Técnico del Proyecto - CodeMio Backend

Este documento proporciona una visión técnica completa del proyecto utilizando diagramas Mermaid para visualizar arquitectura, flujos de trabajo y relaciones entre componentes.

---

## 📐 Arquitectura General del Sistema

```mermaid
graph TB
    subgraph "Cliente"
        FE[Frontend React + Vite]
    end
    
    subgraph "Backend - Django"
        API[API REST<br/>Django REST Framework]
        AUTH[Autenticación<br/>Sistema de Roles]
        PROJ[Gestión de<br/>Proyectos]
        FILE[Gestión de<br/>Archivos]
        ANAL[Servicio de<br/>Análisis]
        LINT[Java Lint<br/>Librería]
    end
    
    subgraph "Persistencia"
        DB[(MySQL<br/>Base de Datos)]
        MEDIA[Media Storage<br/>Archivos .java/.zip]
    end
    
    subgraph "Infraestructura"
        DOCKER[Docker<br/>Contenedorización]
        GHA[GitHub Actions<br/>CI/CD]
        RENDER[Render<br/>Hosting]
    end
    
    FE -->|HTTP/REST| API
    API --> AUTH
    API --> PROJ
    API --> FILE
    API --> ANAL
    ANAL --> LINT
    
    AUTH --> DB
    PROJ --> DB
    FILE --> DB
    FILE --> MEDIA
    ANAL --> DB
    
    DOCKER --> RENDER
    GHA --> DOCKER
    
    style FE fill:#61dafb
    style API fill:#092E20
    style DB fill:#316192
    style DOCKER fill:#2496ED
    style RENDER fill:#46E3B7
```

---

## 🔄 Flujo de Trabajo de Desarrollo

```mermaid
flowchart LR
    subgraph "Desarrollo Local"
        DEV[👨‍💻 Desarrollador]
        CODE[Escribir Código]
        TEST[Ejecutar Tests]
        LINT[Linting<br/>flake8]
    end
    
    subgraph "Control de Versiones"
        COMMIT[Commit<br/>Conventional Commits]
        PUSH[Push a GitHub]
    end
    
    subgraph "CI/CD Pipeline"
        GHA[GitHub Actions]
        BUILD[Build Docker]
        VALIDATE[Validar Tests]
    end
    
    subgraph "Producción"
        RENDER[Render Deploy]
        PROD[🌐 Producción]
    end
    
    DEV --> CODE
    CODE --> TEST
    TEST --> LINT
    LINT --> COMMIT
    COMMIT --> PUSH
    PUSH --> GHA
    GHA --> VALIDATE
    VALIDATE -->|✅ Pass| BUILD
    BUILD -->|✅ Success| RENDER
    RENDER --> PROD
    
    VALIDATE -->|❌ Fail| DEV
    BUILD -->|❌ Fail| DEV
    
    style DEV fill:#FFD700
    style GHA fill:#2088FF
    style PROD fill:#28a745
```

---

## 📊 Modelo de Datos (Entidad-Relación)

```mermaid
erDiagram
    USUARIO ||--o{ PROYECTO : crea
    PROYECTO ||--o{ ARCHIVO : contiene
    PROYECTO ||--o{ METRICA : genera
    ARCHIVO ||--o{ METRICA : analiza
    
    USUARIO {
        int id PK
        string nombre
        int edad
        string correo UK
        string password
        string perfil_github
        enum rol
        datetime fecha_registro
    }
    
    PROYECTO {
        int id PK
        string nombre
        int usuario_id FK
        datetime fecha_creacion
        datetime fecha_modificacion
    }
    
    ARCHIVO {
        int id PK
        string nombre
        int proyecto_id FK
        text contenido
        string ruta_almacenamiento
        datetime fecha_carga
        enum tipo
    }
    
    METRICA {
        int id PK
        int proyecto_id FK
        int archivo_id FK
        json valores_calculados
        json evaluacion
        datetime fecha_analisis
        enum estado
    }
```

---

## 🔐 Flujo de Autenticación

```mermaid
sequenceDiagram
    participant U as Usuario
    participant F as Frontend
    participant A as API Backend
    participant DB as Database
    
    U->>F: Introduce credenciales
    F->>A: POST /api/auth/login
    A->>DB: Verificar usuario
    DB-->>A: Datos del usuario
    
    alt Credenciales válidas
        A-->>F: 200 OK + Token/Session
        F-->>U: Redirigir a Dashboard
    else Credenciales inválidas
        A-->>F: 401 Unauthorized
        F-->>U: Mostrar error
    end
```

---

## 📤 Flujo de Carga y Análisis de Archivos

```mermaid
flowchart TD
    START([Usuario sube archivo]) --> CHECK{Tipo de archivo}
    
    CHECK -->|.java| SINGLE[Procesar archivo único]
    CHECK -->|.zip| MULTI[Descomprimir ZIP]
    
    MULTI --> EXTRACT[Extraer archivos .java]
    EXTRACT --> VALIDATE
    SINGLE --> VALIDATE
    
    VALIDATE[Validar archivos] --> STORE[Guardar en DB y Storage]
    STORE --> QUEUE[Encolar análisis]
    
    QUEUE --> ASYNC[Procesamiento Asíncrono]
    ASYNC --> LINT[Ejecutar Java Lint]
    LINT --> METRICS[Calcular métricas]
    METRICS --> EVAL[Evaluar contra rangos]
    EVAL --> SAVE[Guardar métricas en DB]
    SAVE --> NOTIFY[Notificar completado]
    NOTIFY --> END([Dashboard actualizado])
    
    style START fill:#4CAF50
    style END fill:#2196F3
    style ASYNC fill:#FF9800
    style LINT fill:#9C27B0
```

---

## 🏗️ Arquitectura de Directorios del Proyecto

```mermaid
graph TD
    ROOT[codemio_back/]
    
    ROOT --> CONFIG[codemio_back/<br/>Configuración Django]
    ROOT --> GITHUB[.github/<br/>CI/CD Workflows]
    ROOT --> DOCS[Documentación<br/>*.md]
    ROOT --> DOCKER[Docker<br/>Dockerfile, compose]
    ROOT --> CONF[Configuración<br/>.gitignore, .flake8]
    ROOT --> DEPS[requirements.txt<br/>Dependencias]
    ROOT --> MANAGE[manage.py<br/>CLI Django]
    
    CONFIG --> SETTINGS[settings.py]
    CONFIG --> URLS[urls.py]
    CONFIG --> WSGI[wsgi.py]
    
    GITHUB --> CI[ci.yml<br/>Pipeline CI/CD]
    
    DOCS --> README[README.md]
    DOCS --> COMMANDS[COMMANDS.md]
    DOCS --> SUMMARY[CONFIGURATION_SUMMARY.md]
    DOCS --> MAP[PROJECT_MAP.md]
    
    style ROOT fill:#092E20
    style CONFIG fill:#44B78B
    style DOCS fill:#2196F3
```

---

## 🔄 Pipeline de CI/CD

```mermaid
flowchart TB
    subgraph "Trigger"
        PUSH[Push a main/develop]
        PR[Pull Request]
    end
    
    subgraph "GitHub Actions - Job: Test"
        CHECKOUT1[Checkout código]
        SETUP1[Setup Python 3.12]
        MYSQL[Iniciar MySQL]
        INSTALL1[Instalar dependencias]
        FLAKE[Ejecutar flake8]
        MIGRATE[Ejecutar migraciones]
        TEST[Ejecutar tests]
    end
    
    subgraph "GitHub Actions - Job: Build"
        CHECKOUT2[Checkout código]
        BUILDX[Setup Docker Buildx]
        BUILD[Build imagen Docker]
        TESTIMG[Test imagen]
    end
    
    subgraph "Render"
        DETECT[Detectar push]
        BUILDR[Build en Render]
        DEPLOY[Deploy automático]
        LIVE[🟢 Live]
    end
    
    PUSH --> CHECKOUT1
    PR --> CHECKOUT1
    
    CHECKOUT1 --> SETUP1
    SETUP1 --> MYSQL
    MYSQL --> INSTALL1
    INSTALL1 --> FLAKE
    FLAKE --> MIGRATE
    MIGRATE --> TEST
    
    TEST -->|✅ Pass| CHECKOUT2
    CHECKOUT2 --> BUILDX
    BUILDX --> BUILD
    BUILD --> TESTIMG
    
    TESTIMG -->|✅ Success| DETECT
    DETECT --> BUILDR
    BUILDR --> DEPLOY
    DEPLOY --> LIVE
    
    TEST -->|❌ Fail| FAIL1[❌ Pipeline Failed]
    TESTIMG -->|❌ Fail| FAIL2[❌ Pipeline Failed]
    
    style LIVE fill:#28a745
    style FAIL1 fill:#dc3545
    style FAIL2 fill:#dc3545
```

---

## 🎯 Flujo de Casos de Uso Principales

### Usuario Regular (USER)

```mermaid
flowchart LR
    USER([👤 Usuario])
    
    USER --> REG[Registrarse]
    USER --> LOGIN[Iniciar Sesión]
    USER --> CREATE[Crear Proyecto]
    USER --> UPLOAD[Subir Archivos]
    USER --> VIEW[Ver Métricas]
    USER --> EDIT[Editar Proyecto]
    USER --> DELETE[Eliminar Proyecto]
    
    CREATE --> UPLOAD
    UPLOAD --> ANALYZE[Análisis Automático]
    ANALYZE --> VIEW
    
    style USER fill:#4CAF50
    style ANALYZE fill:#FF9800
```

### Administrador (ADMIN)

```mermaid
flowchart LR
    ADMIN([👑 Admin])
    
    ADMIN --> USERS[Gestión de Usuarios]
    ADMIN --> PROJECTS[Ver Todos los Proyectos]
    ADMIN --> METRICS[Ver Todas las Métricas]
    ADMIN --> REPORTS[Generar Reportes]
    
    USERS --> CREATE[Crear Usuario]
    USERS --> EDIT[Editar Usuario]
    USERS --> DELETE[Eliminar Usuario]
    USERS --> ACTIVATE[Activar/Desactivar]
    
    style ADMIN fill:#9C27B0
    style USERS fill:#2196F3
```

---

## 🌐 API REST - Estructura de Endpoints

```mermaid
graph TB
    ROOT[API Root<br/>/api/]
    
    ROOT --> AUTH[/auth/]
    ROOT --> USERS[/users/]
    ROOT --> PROJECTS[/projects/]
    ROOT --> FILES[/files/]
    ROOT --> METRICS[/metrics/]
    
    AUTH --> LOGIN[POST /login/]
    AUTH --> REGISTER[POST /register/]
    AUTH --> LOGOUT[POST /logout/]
    
    USERS --> LISTUSERS[GET /]
    USERS --> USERDETAIL[GET /:id/]
    USERS --> UPDATEUSER[PUT/PATCH /:id/]
    USERS --> DELETEUSER[DELETE /:id/]
    
    PROJECTS --> LISTPROJ[GET /]
    PROJECTS --> CREATEPROJ[POST /]
    PROJECTS --> PROJDETAIL[GET /:id/]
    PROJECTS --> UPDATEPROJ[PUT/PATCH /:id/]
    PROJECTS --> DELETEPROJ[DELETE /:id/]
    
    FILES --> UPLOADFILE[POST /upload/]
    FILES --> LISTFILES[GET /]
    FILES --> FILEDETAIL[GET /:id/]
    FILES --> DELETEFILE[DELETE /:id/]
    
    METRICS --> LISTMETRICS[GET /]
    METRICS --> METRICDETAIL[GET /:id/]
    METRICS --> PROJMETRICS[GET /project/:id/]
    
    style ROOT fill:#092E20
    style AUTH fill:#4CAF50
    style PROJECTS fill:#2196F3
    style FILES fill:#FF9800
    style METRICS fill:#9C27B0
```

---

## 🐳 Arquitectura Docker

```mermaid
graph TB
    subgraph "Docker Compose - Desarrollo Local"
        WEB[Web Service<br/>Django App<br/>:8000]
        DB[MySQL Service<br/>:3306]
        VOL[Volumen<br/>mysql_data]
    end
    
    subgraph "Dockerfile - Producción"
        BASE[Base: python:3.12-slim]
        DEPS[Instalar dependencias<br/>sistema y Python]
        COPY[Copiar código<br/>del proyecto]
        STATIC[Collectstatic]
        START[Script de inicio<br/>migrate + gunicorn]
    end
    
    WEB --> DB
    DB --> VOL
    
    BASE --> DEPS
    DEPS --> COPY
    COPY --> STATIC
    STATIC --> START
    
    style WEB fill:#092E20
    style DB fill:#316192
    style START fill:#499848
```

---

## 📦 Dependencias del Proyecto

```mermaid
graph LR
    subgraph "Core"
        DJANGO[Django 5.2.11]
        DRF[DRF 3.15.2]
    end
    
    subgraph "Base de Datos"
        PYMYSQL[PyMySQL]
        DBURL[dj-database-url]
    end
    
    subgraph "Servidor"
        GUNICORN[Gunicorn 22.0.0]
    end
    
    subgraph "Configuración"
        DECOUPLE[python-decouple]
        DOTENV[python-dotenv]
        ENVIRON[django-environ]
    end
    
    subgraph "Seguridad y CORS"
        CORS[django-cors-headers]
    end
    
    subgraph "Utilidades"
        PILLOW[Pillow]
    end
    
    DJANGO --> DRF
    DJANGO --> PYMYSQL
    DJANGO --> CORS
    DRF --> DJANGO
    
    style DJANGO fill:#092E20
    style DRF fill:#A30000
    style GUNICORN fill:#499848
```

---

## 🔄 Ciclo de Vida de una Solicitud HTTP

```mermaid
sequenceDiagram
    participant C as Cliente
    participant G as Gunicorn
    participant M as Middleware
    participant V as View/API
    participant S as Serializer
    participant DB as Database
    participant L as Java Lint
    
    C->>G: HTTP Request
    G->>M: Process Request
    M->>M: CORS Check
    M->>M: Authentication
    M->>V: Route to View
    V->>S: Validate Data
    S->>V: Validated Data
    V->>DB: Query/Save
    DB-->>V: Result
    
    alt Análisis requerido
        V->>L: Analyze Code
        L-->>V: Metrics
        V->>DB: Save Metrics
    end
    
    V->>S: Serialize Response
    S-->>V: JSON Data
    V-->>M: Response
    M-->>G: Response
    G-->>C: HTTP Response
```

---

## 📝 Configuración de Variables de Entorno

```mermaid
graph TD
    ENV[.env File]
    
    ENV --> SECRET[SECRET_KEY<br/>Django Secret]
    ENV --> DEBUG[DEBUG<br/>True/False]
    ENV --> HOSTS[ALLOWED_HOSTS<br/>CSV List]
    ENV --> DBURL[DATABASE_URL<br/>MySQL URL]
    ENV --> CORS[CORS_ALLOWED_ORIGINS<br/>Frontend URLs]
    ENV --> PORT[PORT<br/>8000]
    
    SECRET --> DJANGO[Django App]
    DEBUG --> DJANGO
    HOSTS --> DJANGO
    DBURL --> MYSQL_DB[(MySQL)]
    CORS --> MIDDLEWARE[CORS Middleware]
    PORT --> GUNICORN[Gunicorn Server]
    
    style ENV fill:#FFC107
    style DJANGO fill:#092E20
    style MYSQL_DB fill:#4479A1
```

---

## 🔒 Sistema de Roles y Permisos

```mermaid
flowchart TB
    subgraph "Usuario Anónimo"
        ANON[Sin autenticar]
        ANON --> REGVIEW[Ver página de registro]
        ANON --> LOGINVIEW[Ver página de login]
    end
    
    subgraph "Usuario Regular (USER)"
        USER[Autenticado como USER]
        USER --> OWNPROJ[Ver proyectos propios]
        USER --> CREATEPROJ[Crear proyecto]
        USER --> EDITPROJ[Editar proyecto propio]
        USER --> DELPROJ[Eliminar proyecto propio]
        USER --> UPLOAD[Subir archivos]
        USER --> VIEWMETRICS[Ver métricas propias]
    end
    
    subgraph "Administrador (ADMIN)"
        ADMIN[Autenticado como ADMIN]
        ADMIN --> ALLPROJ[Ver TODOS los proyectos]
        ADMIN --> ALLUSERS[Gestión completa de usuarios]
        ADMIN --> ALLMETRICS[Ver TODAS las métricas]
        ADMIN --> ADMINPANEL[Panel de administración]
    end
    
    ANON -.->|Registro| USER
    ANON -.->|Login| USER
    ANON -.->|Login Admin| ADMIN
    
    style ANON fill:#9E9E9E
    style USER fill:#4CAF50
    style ADMIN fill:#9C27B0
```

---

## 🎨 Recursos Estáticos y Media

```mermaid
graph TB
    subgraph "Desarrollo"
        STATIC_DEV[/static/<br/>CSS, JS, Images]
        MEDIA_DEV[/media/<br/>Uploaded Files]
    end
    
    subgraph "Producción"
        COLLECT[python manage.py<br/>collectstatic]
        STATICFILES[/staticfiles/<br/>Archivos estáticos<br/>recolectados]
        MEDIA_PROD[/media/<br/>Archivos subidos]
        
        COLLECT --> STATICFILES
    end
    
    subgraph "Servicio"
        NGINX[Servidor Web<br/>Render/Nginx]
        WHITENOISE[WhiteNoise<br/>Middleware]
    end
    
    STATICFILES --> WHITENOISE
    MEDIA_PROD --> NGINX
    WHITENOISE --> NGINX
    
    style COLLECT fill:#FF9800
    style NGINX fill:#009639
    style WHITENOISE fill:#2196F3
```

---

## 📚 Resumen de Documentación

| Diagrama | Descripción | Uso |
|----------|-------------|-----|
| **Arquitectura General** | Vista completa del sistema | Entender componentes principales |
| **Flujo de Desarrollo** | Workflow de desarrollo | Proceso de contribución |
| **Modelo de Datos** | Relaciones entre entidades | Diseño de base de datos |
| **Autenticación** | Flujo de login/registro | Implementación de seguridad |
| **Carga de Archivos** | Proceso de análisis | Flujo de negocio principal |
| **Directorios** | Estructura del proyecto | Navegación del código |
| **CI/CD Pipeline** | Integración continua | DevOps y despliegue |
| **Casos de Uso** | Flujos por rol | Funcionalidades del sistema |
| **API Endpoints** | Estructura de la API | Desarrollo frontend |
| **Docker** | Contenedorización | Despliegue y desarrollo local |
| **Dependencias** | Librerías del proyecto | Gestión de paquetes |
| **Request Lifecycle** | Ciclo de solicitud HTTP | Debugging y optimización |
| **Variables de Entorno** | Configuración | Setup del proyecto |
| **Roles y Permisos** | Control de acceso | Seguridad |
| **Recursos Estáticos** | Archivos CSS/JS/Media | Producción |

---

## 🔗 Enlaces a Otros Documentos

- [`README.md`](README.md) - Guía principal de instalación y uso
- [`CONFIGURATION_SUMMARY.md`](CONFIGURATION_SUMMARY.md) - Resumen detallado de configuración
- [`COMMANDS.md`](COMMANDS.md) - Referencia rápida de comandos
- [`setup.sh`](setup.sh) - Script de configuración automatizada

---

## 📌 Notas Importantes

> 💡 **Tip:** Los diagramas Mermaid se renderizan automáticamente en GitHub, GitLab, y muchos editores Markdown modernos.

> 🔄 **Actualización:** Este documento debe actualizarse cuando se realicen cambios significativos en la arquitectura del proyecto.

> 📖 **Aprende más:** [Documentación de Mermaid](https://mermaid.js.org/)
