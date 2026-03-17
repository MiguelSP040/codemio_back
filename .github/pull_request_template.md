---
name: 🔄 Pull Request
about: Template para Pull Requests en CodeMio Backend
title: '[TIPO] Breve descripción del cambio'
labels: ''
assignees: ''
---

## 📋 Información del Pull Request

### 🏷️ Versión y Ambiente

- **Versión:** v0.0.0 <!-- Especifica la versión del proyecto -->
- **Ambiente afectado:** 
  - [ ] Desarrollo
  - [ ] Producción
- **Rama base:** `main` / `develop` / `otra`
- **Rama feature:** `feat/nombre-de-la-feature`

---

### 📝 Descripción

<!-- Proporciona una descripción clara y concisa de los cambios realizados -->

**¿Qué hace este PR?**


**¿Por qué es necesario este cambio?**


**¿Qué problema resuelve?**


---

### 🔄 Pasos para Reproducir / Probar

<!-- Lista los pasos para probar los cambios realizados -->

1. 
2. 
3. 
4. 

**Comandos para testing:**
```bash
# Ejemplo:
python manage.py test
python manage.py runserver
```

---

### 🎫 Ticket Relacionado

<!-- Enlaza el issue o ticket relacionado -->

- **Issue:** Closes #<!-- número del issue -->
- **Jira/Trello:** <!-- Enlace al ticket externo si aplica -->
- **Documentación:** <!-- Enlace a documentación relacionada -->

---

### 📸 Capturas de Pantalla

<!-- Si aplica, agrega capturas de pantalla de la funcionalidad -->

**Antes:**
<!-- Imagen del estado anterior -->

**Después:**
<!-- Imagen del nuevo estado -->

---

### ℹ️ Información Adicional

#### 🔧 Cambios Técnicos

- **Archivos modificados:** 
  - `ruta/al/archivo.py`
  - `ruta/al/otro/archivo.py`

- **Nuevas dependencias:** 
  - [ ] No se agregaron nuevas dependencias
  - [ ] Sí, se agregaron: <!-- listar dependencias -->

- **Migraciones de BD:**
  - [ ] No requiere migraciones
  - [ ] Sí, requiere ejecutar: `python manage.py migrate`

- **Variables de entorno:**
  - [ ] No requiere nuevas variables
  - [ ] Sí, requiere agregar al `.env`: <!-- listar variables -->

#### 🧪 Testing

- [ ] Tests unitarios agregados/actualizados
- [ ] Tests de integración agregados/actualizados
- [ ] Todos los tests existentes pasan
- [ ] Coverage se mantiene o mejora

```bash
# Resultado de tests
# Pega aquí el resultado de ejecutar los tests
```

#### 📚 Documentación

- [ ] README.md actualizado (si aplica)
- [ ] COMMANDS.md actualizado (si aplica)
- [ ] Docstrings agregados/actualizados
- [ ] CONFIGURATION_SUMMARY.md actualizado (si aplica)
- [ ] PROJECT_MAP.md actualizado (si aplica)

#### 🎯 Checklist

- [ ] El código sigue las convenciones de [Conventional Commits](https://www.conventionalcommits.org/)
- [ ] He realizado self-review de mi código
- [ ] He comentado el código en áreas complejas
- [ ] Mis cambios no generan nuevos warnings
- [ ] El linting pasa sin errores (`flake8`)
- [ ] He actualizado la documentación relevante
- [ ] Mis cambios no rompen funcionalidad existente

#### 🔒 Seguridad

- [ ] No se exponen credenciales o información sensible
- [ ] Se siguen las mejores prácticas de seguridad
- [ ] Las variables sensibles están en `.env`
- [ ] No se hace commit de archivos `.env`

#### ⚡ Performance

- [ ] No se identifican problemas de performance
- [ ] Se consideraron optimizaciones necesarias
- [ ] Las queries a BD están optimizadas

---

### 👥 Reviewers

<!-- Tag a las personas que deberían revisar este PR -->

@<!-- username1 --> @<!-- username2 -->

---

### 🚀 Deployment

- [ ] Listo para merge a develop
- [ ] Listo para merge a main
- [ ] Requiere deployment manual
- [ ] Requiere configuración adicional en producción

**Notas de deployment:**
<!-- Cualquier consideración especial para el deployment -->

---

### 📝 Notas Adicionales

<!-- Cualquier información adicional que los reviewers deban saber -->

---

### 🏁 Post-Merge Checklist

- [ ] Verificar deployment exitoso
- [ ] Monitorear logs por errores
- [ ] Verificar métricas de performance
- [ ] Actualizar stakeholders
- [ ] Cerrar issue relacionado

---

**Tipo de cambio:**
- [ ] 🐛 Bug fix
- [ ] ✨ Nueva funcionalidad
- [ ] 💥 Breaking change
- [ ] 📝 Documentación
- [ ] 🎨 Mejora de UI/UX
- [ ] ⚡ Mejora de performance
- [ ] ♻️ Refactorización
- [ ] 🔧 Configuración
- [ ] 🔒 Seguridad

---

_Template version: 1.0.0_
