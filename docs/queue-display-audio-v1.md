# Audio de QueueDisplay (0048)

0048 añade una capa opcional de voz a la pantalla pública. La síntesis se ejecuta
con Web Speech API en el navegador de la TV; no hay servicio TTS, audio grabado ni
envío deliberado de contenido a un proveedor externo. Solo se seleccionan voces
españolas que el navegador declare locales (`localService`); si no hay una,
el audio queda no disponible y la pantalla visual continúa. Conviene validar
la voz instalada en el dispositivo antes de usarla en el piloto. La configuración pertenece a cada
`QueueDisplay` y el audio está desactivado por defecto.

La respuesta pública conserva la lista permitida de 0047 y añade únicamente
`call_revision` (el contador de llamadas del ticket) y las opciones de audio.
La identidad de anuncio combina código público, `called_at` y revisión. Una
rellamada incrementa la revisión; el polling de tres segundos no repite la misma
identidad. La primera carga marca las llamadas visibles como ya vistas y no las
pronuncia. No se cambian `QueueTicket`, eventos, estados ni flujo de llamada.

La frase por defecto contiene solo código público y destino. Servicio y proveedor
se pronuncian únicamente si se habilitan las opciones de audio **y** las opciones
de visibilidad correspondientes de 0047. Nunca se incluyen paciente, teléfono,
identificadores clínicos, motivo o información financiera.

El operador debe pulsar «Activar audio» en el dispositivo. Antes de cada llamada
nueva se emite un aviso tonal breve y se deja una pausa de 150 ms antes de la
frase. Esto prepara la salida HDMI frente al recorte observado al iniciar una
voz en frío; no sustituye una comprobación audible en el proyector/TV. Si Web
Audio no está disponible, la voz continúa sin el aviso previo. Los navegadores pueden
exigir esta interacción incluso si el audio se usó antes; no se garantiza autoplay.
Si no existe `speechSynthesis` o falla, la pantalla visual continúa funcionando.
Las llamadas simultáneas se encolan y cada repetición termina antes de la
siguiente. Un lease en `localStorage` y mensajes `BroadcastChannel` coordinan
pestañas del mismo navegador; los anuncios ya iniciados se recuerdan localmente
para evitar duplicados al cambiar de líder. Esta coordinación no se extiende a
dispositivos o navegadores distintos.

La migración `0048_queue_display_audio` es aditiva: agrega ajustes y checks a
`queue_displays`, con defaults seguros para pantallas existentes. Está aplicada
en la base local oficial. El downgrade se valida solo en PostgreSQL desechable.

`0049_queue_display_voice` agrega una preferencia opcional `audio_voice_uri` por
pantalla. La selecciona únicamente un administrador autorizado en Seguridad;
el backend la almacena y la pantalla pública busca una coincidencia exacta
entre las voces españolas **locales** del navegador que reproduce el audio.
Nunca se acepta una voz remota como sustituto. Si la voz elegida no está
instalada en la PC de la TV, la pantalla indica que no está disponible y
continúa mostrando los turnos sin sonido. El modo automático (`null`) conserva
la selección local de 0048. La API de navegador expone nombre e idioma/acento,
pero no género; por ello el panel incluye una prueba audible y no promete
catálogos femenino/masculino o latinoamericanos que el sistema no tenga.
La preferencia es de la pantalla, no del administrador que la configuró.

`0050_queue_display_repeat_limit` amplía de 1–3 a 1–10 el número finito de
repeticiones por cada llamada. Se configura por pantalla en Administración →
Localidades y centros → Pantallas de turnos. Se aplica también a «Volver a
llamar»; pulsar RECALL una vez crea un único evento nuevo cuyo anuncio se
pronuncia la cantidad configurada. El intervalo entre repeticiones sigue siendo
configurable. El valor existente 1 se conserva hasta que el administrador lo
cambie. El downgrade a 0049 se bloquea si alguna pantalla usa más de 3.
