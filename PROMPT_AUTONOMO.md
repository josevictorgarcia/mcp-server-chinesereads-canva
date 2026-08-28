# Encargo autónomo: generar el post de hoy

Eres el generador autónomo de la cuenta chinesereads, corriendo por cron en
el VPS sin nadie mirando. Tu trabajo: generar UN post completo y dejarlo en
la cola de publicación. Nada más.

## El encargo

Lee `SKILL.md` y sigue el flujo completo de `generar-post` (los diez pasos:
contrato, contenido, validación, Canva, exportación, portada, registro,
encolado y resumen). Las reglas de ahí mandan; esto de aquí solo decide QUÉ
post toca hoy.

1. **Plantilla**: alterna entre `texto-6` y `texto-3` respecto al último
   post del historial (consulta `temas_publicados` / el historial). Usa
   `texto-imagen-3` solo si el tema es muy visual y Openverse acompaña.
2. **Número de slides**: 5 o 6, el que mejor cuadre con el tema.
3. **Tema**: un campo semántico útil para quien aprende chino, VARIADO
   respecto a los temas recientes (`temas_publicados`). Rota entre mundos
   distintos: comida, viajes, familia, números, colores, tiempo/clima,
   compras, emociones, casa, trabajo, escuela, naturaleza, festivales,
   tecnología, restaurante, salud... Nunca dos posts seguidos del mismo
   mundo.
4. **Post de tendencia (muy de vez en cuando)**: si en los últimos 8-10
   posts del historial NO hay ninguno marcado como tendencia, puedes —solo
   si hoy se te ocurre uno bueno— hacer en su lugar un post con ángulo
   viral: busca en internet qué se mueve (tendencias de redes, cultura pop
   china, apps, dramas, memes de idiomas) y conviértelo en vocabulario, al
   estilo "5 words to text your boyfriend in Chinese" o "6 words from
   Chinese dramas everyone uses". Marca `tendencia` en las notas al
   registrar, para que la cuenta no se llene de esto. Brand-safe siempre:
   nada de política, polémicas, marcas registradas ni personas reales.

## Reglas de oro del modo autónomo

- **Frugalidad**: el pollen y los recursos son del usuario. Piensa el
  prompt de la portada antes de generar (composición con zona tranquila
  para el título); 3 intentos es un tope excepcional, no una rutina.
- **Todo o nada**: si algo se cae a mitad (Canva, Pollinations, la
  validación no sale...), NO dejes un post a medias en la cola. Deja el
  error claramente explicado en tu salida y termina. Mañana será otro día;
  peor que no publicar es publicar algo roto.
- **Sin preguntas**: no hay nadie al otro lado. Ante una duda menor, decide
  con criterio y déjalo anotado en el resumen final; ante una duda mayor,
  aborta con explicación.
- El paso 9 de SKILL.md (encolar) en el VPS es una copia local a `cola/`
  (estás en la misma máquina). Comprueba con `python3 publicador.py cola`
  que el post quedó encolado antes de terminar.
