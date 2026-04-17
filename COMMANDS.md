# 🛠️ Comandos Útiles - CodeMio Backend

Referencia rápida de comandos útiles para el desarrollo del proyecto.

---

## 📦 Entorno Virtual

### Crear y Activar
```bash
# Crear entorno virtual
python3 -m venv venv

# Activar (Linux/macOS)
source venv/bin/activate

# Activar (Windows)
venv\Scripts\activate

# Desactivar
deactivate
```

### Dependencias
```bash
# Instalar dependencias
pip install -r requirements.txt

# Instalar un paquete nuevo
pip install nombre-paquete

# Guardar dependencias actuales
pip freeze > requirements.txt

# Actualizar pip
pip install --upgrade pip

# Listar paquetes instalados
pip list

# Mostrar info de un paquete
pip show nombre-paquete

# Desinstalar paquete
pip uninstall nombre-paquete
```

---

## 🐍 Django

### Gestión del Proyecto
```bash
# Verificar configuración
python manage.py check

# Iniciar servidor de desarrollo
python manage.py runserver

# Iniciar servidor en puerto específico
python manage.py runserver 8080

# Iniciar servidor accesible desde red local
python manage.py runserver 0.0.0.0:8000

# Shell interactivo de Django
python manage.py shell

# Shell con IPython (si está instalado)
python manage.py shell -i ipython

# Mostrar SQL de las migraciones
python manage.py sqlmigrate app_name 0001
```

### Migraciones
```bash
# Crear migraciones
python manage.py makemigrations

# Crear migración para una app específica
python manage.py makemigrations app_name

# Crear migración vacía
python manage.py makemigrations --empty app_name

# Aplicar migraciones
python manage.py migrate

# Aplicar migraciones de una app específica
python manage.py migrate app_name

# Ver estado de migraciones
python manage.py showmigrations

# Revertir a una migración específica
python manage.py migrate app_name 0001

# Ver SQL que se ejecutará
python manage.py sqlmigrate app_name 0001
```

### Base de Datos
```bash
# Abrir shell de base de datos
python manage.py dbshell

# Volcar datos en JSON
python manage.py dumpdata > data.json

# Volcar datos de una app específica
python manage.py dumpdata app_name > app_data.json

# Cargar datos desde JSON
python manage.py loaddata data.json

# Resetear base de datos (¡CUIDADO en producción!)
python manage.py flush
```

### Usuarios
```bash
# Crear superusuario
python manage.py createsuperuser

# Cambiar contraseña de usuario
python manage.py changepassword username
```

### Apps
```bash
# Crear nueva app
python manage.py startapp app_name

# Listar apps instaladas
python manage.py diffsettings | grep INSTALLED_APPS
```

### Archivos Estáticos
```bash
# Recolectar archivos estáticos
python manage.py collectstatic

# Recolectar sin confirmación
python manage.py collectstatic --noinput

# Limpiar archivos estáticos antiguos
python manage.py collectstatic --clear
```

---

## 🧪 Testing

### Django Tests
```bash
# Ejecutar todos los tests
python manage.py test

# Ejecutar tests de una app
python manage.py test app_name

# Ejecutar tests con verbosidad
python manage.py test --verbosity=2

# Mantener base de datos de tests
python manage.py test --keepdb

# Ejecutar tests en paralelo
python manage.py test --parallel

# Ejecutar un test específico
python manage.py test app_name.tests.TestClass.test_method
```

### Pytest (si está configurado)
```bash
# Ejecutar todos los tests
pytest

# Con verbosidad
pytest -v

# Con coverage
pytest --cov=.

# Ejecutar un archivo específico
pytest tests/test_file.py

# Ejecutar un test específico
pytest tests/test_file.py::test_function
```

### Coverage
```bash
# Instalar coverage
pip install coverage

# Ejecutar tests con coverage
coverage run --source='.' manage.py test

# Ver reporte en terminal
coverage report

# Generar reporte HTML
coverage html

# Abrir reporte HTML
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

---

## 🐳 Docker

### Build y Run
```bash
# Construir imagen
docker build -t codemio-backend .

# Construir sin cache
docker build --no-cache -t codemio-backend .

# Ejecutar contenedor
docker run -p 8000:8000 codemio-backend

# Ejecutar con variables de entorno
docker run -p 8000:8000 --env-file .env codemio-backend

# Ejecutar en modo detached
docker run -d -p 8000:8000 --name codemio codemio-backend

# Ejecutar en modo interactivo
docker run -it -p 8000:8000 codemio-backend /bin/bash
```

### Gestión de Contenedores
```bash
# Listar contenedores activos
docker ps

# Listar todos los contenedores
docker ps -a

# Detener contenedor
docker stop codemio

# Iniciar contenedor detenido
docker start codemio

# Reiniciar contenedor
docker restart codemio

# Eliminar contenedor
docker rm codemio

# Eliminar contenedor forzadamente
docker rm -f codemio

# Ver logs del contenedor
docker logs codemio

# Seguir logs en tiempo real
docker logs -f codemio

# Ejecutar comando en contenedor activo
docker exec -it codemio python manage.py migrate

# Acceder a shell del contenedor
docker exec -it codemio /bin/bash
```

### Imágenes
```bash
# Listar imágenes
docker images

# Eliminar imagen
docker rmi codemio-backend

# Eliminar imágenes sin usar
docker image prune

# Eliminar todas las imágenes
docker rmi $(docker images -q)
```

### Docker Compose
```bash
# Iniciar servicios
docker-compose up

# Iniciar en modo detached
docker-compose up -d

# Reconstruir imágenes
docker-compose up --build

# Detener servicios
docker-compose down

# Detener y eliminar volúmenes
docker-compose down -v

# Ver logs
docker-compose logs

# Seguir logs
docker-compose logs -f

# Ejecutar comando en servicio
docker-compose exec web python manage.py migrate

# Listar servicios
docker-compose ps

# Reconstruir un servicio específico
docker-compose build web
```

---

## 🔍 Linting y Formateo

### Flake8
```bash
# Instalar flake8
pip install flake8

# Ejecutar flake8
flake8 .

# Ignorar directorios específicos
flake8 --exclude=venv,migrations .

# Ver solo errores críticos
flake8 --select=E9,F63,F7,F82 .

# Con archivo de configuración (.flake8)
flake8
```

### Black (Formateador)
```bash
# Instalar black
pip install black

# Formatear código
black .

# Ver cambios sin aplicar
black --check .

# Formatear archivo específico
black file.py
```

### isort (Ordenar imports)
```bash
# Instalar isort
pip install isort

# Ordenar imports
isort .

# Ver cambios sin aplicar
isort --check-only .
```

---

## 📊 Git

### Commits (Conventional Commits)
```bash
# Añadir archivos
git add .

# Commit siguiendo convención
git commit -m "feat: add user authentication"
git commit -m "fix: resolve database connection issue"
git commit -m "docs: update README"
git commit -m "refactor: simplify user model"

# Commit con body
git commit -m "feat: add JWT authentication" -m "Implements token-based authentication using JWT"

# Ver estado
git status

# Ver historial
git log --oneline
```

### Ramas
```bash
# Crear rama
git checkout -b feature/new-feature

# Cambiar de rama
git checkout main

# Listar ramas
git branch

# Eliminar rama
git branch -d feature/old-feature

# Push de rama
git push origin feature/new-feature
```

### Remote
```bash
# Ver remotes
git remote -v

# Añadir remote
git remote add origin <url>

# Pull cambios
git pull origin main

# Push cambios
git push origin main

# Fetch cambios sin merge
git fetch origin
```

---

## 🗄️ MySQL

### Acceso Directo
```bash
# Conectar a MySQL local
mysql -u username -p database_name

# Conectar con URL
mysql -h localhost -P 3306 -u user -p database

# Listar bases de datos
SHOW DATABASES;

# Usar base de datos
USE database_name;

# Listar tablas
SHOW TABLES;

# Describir tabla
DESCRIBE table_name;

# Ejecutar SQL desde archivo
mysql -u username -p database < script.sql

# Salir
exit;
```

### Backup y Restore
```bash
# Hacer backup
mysqldump -u username -p database_name > backup.sql

# Restaurar backup
mysql -u username -p database_name < backup.sql

# Backup comprimido
mysqldump -u username -p database_name | gzip > backup.sql.gz

# Restaurar comprimido
gunzip -c backup.sql.gz | mysql -u username -p database_name
```

---

## 🚀 Render (Producción)

### Render CLI
```bash
# Instalar Render CLI
npm install -g @render/cli

# Login
render login

# Ver servicios
render services

# Ver logs en tiempo real
render logs <service-name>

# Ejecutar comando en servicio
render shell <service-name>
```

### Comandos Comunes en Shell de Render
```bash
# Acceder al shell
# (desde Render Dashboard > Service > Shell)

# Ejecutar migraciones
python manage.py migrate

# Crear superusuario
python manage.py createsuperuser

# Recolectar estáticos
python manage.py collectstatic --noinput

# Shell de Django
python manage.py shell

# Verificar configuración
python manage.py check
```

---

## 🔧 Utilidades del Sistema

### Linux/macOS
```bash
# Ver procesos en puerto 8000
lsof -i :8000

# Matar proceso en puerto 8000
kill -9 $(lsof -t -i :8000)

# Ver espacio en disco
df -h

# Ver uso de memoria
free -h  # Linux
vm_stat  # macOS

# Buscar archivos
find . -name "*.py"

# Buscar en contenido de archivos
grep -r "search_term" .

# Contar líneas de código
find . -name "*.py" | xargs wc -l
```

### Variables de Entorno
```bash
# Ver todas las variables
printenv

# Ver variable específica
echo $DATABASE_URL

# Establecer variable temporalmente
export DATABASE_URL="mysql://..."

# Establecer variable permanentemente (Linux/macOS)
echo 'export DATABASE_URL="..."' >> ~/.bashrc
source ~/.bashrc
```

---

## 📝 Generadores Útiles

### SECRET_KEY
```bash
# Generar SECRET_KEY para Django
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"

# Alternativa con Python
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

### UUID
```bash
# Generar UUID
python -c "import uuid; print(uuid.uuid4())"

# Generar múltiples UUIDs
python -c "import uuid; [print(uuid.uuid4()) for _ in range(5)]"
```

---

## 🔄 Workflow Completo de Desarrollo

```bash
# 1. Inicio del día
cd codemio_back
git pull origin main
source venv/bin/activate

# 2. Crear feature branch
git checkout -b feat/new-feature

# 3. Desarrollar
python manage.py runserver

# 4. Hacer migraciones (si hay cambios en modelos)
python manage.py makemigrations
python manage.py migrate

# 5. Ejecutar tests
python manage.py test

# 6. Linting
flake8

# 7. Commit
git add .
git commit -m "feat: add new feature"

# 8. Push
git push origin feat/new-feature

# 9. Crear Pull Request en GitHub

# 10. Después del merge
git checkout main
git pull origin main
git branch -d feat/new-feature
```

---

## 🆘 Troubleshooting

### Puerto en Uso
```bash
# Encontrar y matar proceso
lsof -i :8000
kill -9 <PID>

# O en un solo comando
kill -9 $(lsof -t -i :8000)
```

### Problemas con Migraciones
```bash
# Ver estado de migraciones
python manage.py showmigrations

# Revertir a migración anterior
python manage.py migrate app_name 0001

# Fake una migración (marcar como aplicada sin ejecutar)
python manage.py migrate --fake app_name 0002

# Recrear migraciones (¡CUIDADO!)
find . -path "*/migrations/*.py" -not -name "__init__.py" -delete
find . -path "*/migrations/*.pyc" -delete
python manage.py makemigrations
python manage.py migrate
```

### Cache de Python
```bash
# Limpiar cache de Python
find . -type d -name "__pycache__" -exec rm -r {} +
find . -type f -name "*.pyc" -delete
find . -type f -name "*.pyo" -delete
```

### Problemas con Docker
```bash
# Limpiar todo Docker
docker system prune -a

# Ver uso de espacio
docker system df

# Eliminar volúmenes huérfanos
docker volume prune
```

---

## 📚 Recursos Adicionales

- [Django Documentation](https://docs.djangoproject.com/)
- [DRF Documentation](https://www.django-rest-framework.org/)
- [Docker Documentation](https://docs.docker.com/)
- [Render Documentation](https://render.com/docs)
- [MySQL Documentation](https://dev.mysql.com/doc/)
