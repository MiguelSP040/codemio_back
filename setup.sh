#!/bin/bash

# Script de instalación y configuración del entorno de desarrollo

set -e

echo "🚀 Configurando entorno de desarrollo para CodeMio Backend..."

# Colores para output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Verificar que Python esté instalado
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 no está instalado. Por favor, instálalo primero."
    exit 1
fi

echo -e "${GREEN}✓${NC} Python 3 encontrado: $(python3 --version)"

# Crear entorno virtual si no existe
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual..."
    python3 -m venv venv
    echo -e "${GREEN}✓${NC} Entorno virtual creado"
else
    echo -e "${YELLOW}⚠${NC} El entorno virtual ya existe"
fi

# Activar entorno virtual
echo "🔌 Activando entorno virtual..."
source venv/bin/activate

# Actualizar pip
echo "📦 Actualizando pip..."
pip install --upgrade pip

# Instalar dependencias
echo "📦 Instalando dependencias..."
pip install -r requirements.txt

# Crear archivo .env si no existe
if [ ! -f ".env" ]; then
    echo "⚙️  Creando archivo .env desde .env.example..."
    cp .env.example .env
    
    # Generar SECRET_KEY
    SECRET_KEY=$(python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")
    
    # Actualizar SECRET_KEY en .env
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' "s/your-secret-key-here-generate-a-new-one/$SECRET_KEY/" .env
    else
        # Linux
        sed -i "s/your-secret-key-here-generate-a-new-one/$SECRET_KEY/" .env
    fi
    
    echo -e "${GREEN}✓${NC} Archivo .env creado con SECRET_KEY generada"
else
    echo -e "${YELLOW}⚠${NC} El archivo .env ya existe"
fi

# Ejecutar migraciones
echo "🗄️  Ejecutando migraciones..."
python manage.py migrate

echo ""
echo -e "${GREEN}✅ ¡Configuración completada exitosamente!${NC}"
echo ""
echo "Para iniciar el servidor de desarrollo, ejecuta:"
echo "  source venv/bin/activate"
echo "  python manage.py runserver"
echo ""
echo "Para crear un superusuario, ejecuta:"
echo "  python manage.py createsuperuser"
echo ""
