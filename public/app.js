/**
 * Conecta el Paso 1 del informe con el backend de ingesta.
 *
 * Sustituye la maqueta por el flujo real: autenticación del docente, subida de
 * los archivos a Cloud Storage y llamada a la Cloud Function que ejecuta la
 * ingesta. Cuando termina, navega al informe que sirve el backend con el
 * objeto `D` de ese curso ya inyectado (guía §3).
 *
 * Si `firebase-config.js` no existe, no hace nada: el informe queda tal como
 * lo entrega el prototipo, con los datos de ejemplo y la maqueta de carga.
 */

const SDK = "https://www.gstatic.com/firebasejs/10.12.2";

/** Ranura del backend que corresponde a cada casillero del Paso 1. */
const RANURAS = {
  dia: "dia_oficial",
  est: "estudiantes",
  rec: "recomendaciones",
  jump: "seguimiento",
  plan: "plan_anual",
};

/** Ruta con la que el backend sirve un informe ya generado. */
const RUTA_INFORME = "/api/informe";

const proto = window.InformeDIA;
if (proto) arrancar().catch(reportarFallo);

async function arrancar() {
  // Un informe ya generado no necesita el Paso 1: los archivos se procesaron y
  // volver a mostrar el formulario invita a subirlos de nuevo sin motivo.
  if (location.pathname.startsWith(RUTA_INFORME)) {
    document.getElementById("uploadPanel")?.remove();
    return;
  }

  let config;
  try {
    config = await import("/firebase-config.js");
  } catch {
    // Modo autónomo: es un estado válido, no un error. El texto de la maqueta
    // que trae el prototipo ya describe correctamente esta situación.
    return;
  }

  activarModoReal();

  const [{ initializeApp }, auth, storage, functions] = await Promise.all([
    import(`${SDK}/firebase-app.js`),
    import(`${SDK}/firebase-auth.js`),
    import(`${SDK}/firebase-storage.js`),
    import(`${SDK}/firebase-functions.js`),
  ]);

  const app = initializeApp(config.firebaseConfig);
  if (config.appCheckSiteKey) {
    const check = await import(`${SDK}/firebase-app-check.js`);
    check.initializeAppCheck(app, {
      provider: new check.ReCaptchaV3Provider(config.appCheckSiteKey),
      isTokenAutoRefreshEnabled: true,
    });
  }

  const sesion = auth.getAuth(app);
  const bucket = storage.getStorage(app);
  const fns = functions.getFunctions(app, config.region);

  // Si se volvió de un acceso por redirección, hay que consumir el resultado
  // antes de decidir qué pintar; si no, el primer render diría "sin sesión".
  await auth.getRedirectResult(sesion).catch(reportarFallo);

  const acceso = crearBotonAcceso(() => iniciarSesion(auth, sesion));
  let conectado = false;

  auth.onAuthStateChanged(sesion, (usuario) => {
    if (!usuario) {
      acceso.pedirAcceso();
      return;
    }
    acceso.confirmarAcceso(usuario);
    // El observador se dispara también al refrescar el token: sin esta guarda
    // se volverían a enganchar los manejadores sobre los mismos elementos.
    if (conectado) return;
    conectado = true;
    conectarCasilleros(storage, bucket, usuario);
    conectarBotonGenerar(functions, fns, usuario);
  });
}

/**
 * Inicia sesión, siempre desde un clic del docente.
 *
 * El popup debe abrirse dentro del gesto que lo pidió: invocado al cargar la
 * página, el navegador lo bloquea sin excepción (`auth/popup-blocked`). Si aun
 * así lo bloquea —hay navegadores y webviews que los prohíben por completo— se
 * cae a la redirección, que no necesita ventana nueva.
 */
async function iniciarSesion(auth, sesion) {
  const proveedor = new auth.GoogleAuthProvider();
  try {
    await auth.signInWithPopup(sesion, proveedor);
  } catch (error) {
    const codigo = error?.code || "";
    // Cerrar la ventana es una decisión del docente, no un fallo que reportar.
    if (codigo === "auth/popup-closed-by-user" || codigo === "auth/cancelled-popup-request") {
      return;
    }
    if (
      codigo === "auth/popup-blocked" ||
      codigo === "auth/operation-not-supported-in-this-environment"
    ) {
      await auth.signInWithRedirect(sesion, proveedor);
      return;
    }
    throw error;
  }
}

/**
 * Pone el botón de acceso en el Paso 1 y bloquea los casilleros hasta que haya
 * sesión: subir un archivo sin `uid` lo rechazan las reglas de Storage, y es
 * mejor no ofrecer la acción que dejar que falle.
 */
function crearBotonAcceso(alHacerClic) {
  const acciones = document.querySelector(".srcactions");
  const generar = document.getElementById("genBtn");
  const pista = document.getElementById("srchint");

  const boton = document.createElement("button");
  boton.className = "genbtn";
  boton.type = "button";
  boton.textContent = "Iniciar sesión con Google";
  boton.onclick = async () => {
    boton.disabled = true;
    boton.textContent = "Abriendo acceso…";
    try {
      await alHacerClic();
    } catch (error) {
      reportarFallo(error);
    } finally {
      boton.disabled = false;
      boton.textContent = "Iniciar sesión con Google";
    }
  };
  acciones.insertBefore(boton, generar);

  const identidad = document.createElement("span");
  identidad.className = "mockflag";
  identidad.hidden = true;
  document.querySelector(".srchead")?.appendChild(identidad);

  const bloquearCasilleros = (bloqueado) => {
    document.querySelectorAll(".srcslot").forEach((slot) => {
      slot.style.opacity = bloqueado ? ".45" : "";
      slot.style.pointerEvents = bloqueado ? "none" : "";
      const entrada = slot.querySelector('input[type="file"]');
      if (entrada) entrada.disabled = bloqueado;
    });
  };

  return {
    pedirAcceso() {
      boton.hidden = false;
      generar.hidden = true;
      identidad.hidden = true;
      bloquearCasilleros(true);
      pista.style.color = "";
      pista.textContent = "Inicie sesión para subir los archivos de su curso.";
    },
    confirmarAcceso(usuario) {
      boton.hidden = true;
      generar.hidden = false;
      identidad.hidden = false;
      identidad.textContent = usuario.email || usuario.uid;
      bloquearCasilleros(false);
      pista.style.color = "";
      // `updateGen` es el dueño de este texto: dice qué archivos faltan.
      proto.updateGen();
    },
  };
}

/**
 * Deriva el identificador del curso desde los datos que ya muestra el informe.
 * El backend lo valida igual: aquí sólo se evita una ida y vuelta inútil.
 */
function cursoId() {
  const { rbd, curso } = proto.D.meta;
  return `${rbd}-${curso}`.toLowerCase().replace(/[°\s]/g, "");
}

/** Cada casillero sube su archivo en cuanto se selecciona. */
function conectarCasilleros(storage, bucket, usuario) {
  document.querySelectorAll(".srcslot").forEach((slot) => {
    const id = slot.dataset.id;
    const input = slot.querySelector('input[type="file"]');
    const pill = slot.querySelector(".spill");
    const nombreArchivo = slot.querySelector(".sfile");

    input.onchange = async (evento) => {
      const archivo = evento.target.files?.[0];
      if (!archivo) return;

      slot.classList.remove("ok");
      nombreArchivo.textContent = "✓ " + archivo.name;
      pill.textContent = "Subiendo…";
      delete proto.loaded[id];
      proto.updateGen();

      const ruta = `cursos/${usuario.uid}/${cursoId()}/${RANURAS[id]}/${archivo.name}`;
      try {
        await storage.uploadBytes(storage.ref(bucket, ruta), archivo, {
          contentType: archivo.type || "application/octet-stream",
        });
        proto.loaded[id] = archivo.name;
        slot.classList.add("ok");
        pill.textContent = "Cargado";
      } catch (error) {
        pill.textContent = "Error al subir";
        reportarFallo(error);
      }
      proto.updateGen();
    };
  });
}

/** «Generar informe» ejecuta la ingesta y abre el informe del curso. */
function conectarBotonGenerar(functions, fns, usuario) {
  const boton = document.getElementById("genBtn");
  const pista = document.getElementById("srchint");

  boton.onclick = async () => {
    const etiqueta = boton.textContent;
    boton.disabled = true;
    boton.textContent = "Procesando archivos…";
    pista.textContent = "Leyendo el informe DIA y las planillas. Puede tardar un minuto.";

    try {
      const generar = functions.httpsCallable(fns, "generar_informe");
      const { data } = await generar({ cursoId: cursoId() });
      mostrarAvisos(data.avisos || []);
      // El informe lo arma el backend: se navega al HTML con `D` inyectado.
      location.href = `/api/informe?uid=${encodeURIComponent(usuario.uid)}&curso=${
        encodeURIComponent(data.cursoId)
      }`;
    } catch (error) {
      boton.disabled = false;
      boton.textContent = etiqueta;
      // El mensaje del backend dice qué columna falta y en qué archivo.
      pista.textContent = error?.message || "No se pudo generar el informe.";
      pista.style.color = "var(--r)";
    }
  };
}

/** Los avisos no son errores: son los supuestos que tomó la ingesta. */
function mostrarAvisos(avisos) {
  if (!avisos.length) return;
  const panel = document.getElementById("uploadPanel");
  const caja = document.createElement("div");
  caja.className = "note";
  caja.innerHTML =
    `<b>${avisos.length} aviso(s) de la ingesta.</b> El informe se generó igual; ` +
    "revise estos puntos antes de compartirlo.<ul>" +
    avisos.map((a) => `<li>${escapar(a)}</li>`).join("") +
    "</ul>";
  panel.appendChild(caja);
}

/**
 * Corrige el texto del Paso 1 cuando hay backend.
 *
 * El prototipo se describe a sí mismo como maqueta —era cierto— y dejar ese
 * texto con la ingesta conectada haría que el docente no confíe en el informe
 * que acaba de generar.
 */
function activarModoReal() {
  const bandera = document.getElementById("mockflag");
  if (bandera) bandera.textContent = "Carga conectada";

  const bajada = document.getElementById("uploadLead");
  if (bajada) {
    bajada.innerHTML =
      "Sube los archivos del curso y el sistema genera el informe automáticamente. " +
      "Los archivos se procesan en el servidor: se leen el informe oficial DIA y las " +
      "planillas, y se calculan los resultados con las reglas del programa. " +
      "Mientras tanto se muestra el último informe generado para este curso.";
  }
}

function escapar(texto) {
  const nodo = document.createElement("span");
  nodo.textContent = texto;
  return nodo.innerHTML;
}

function reportarFallo(error) {
  console.error("[InformeDIA]", error);
  const pista = document.getElementById("srchint");
  if (pista) {
    pista.textContent = error?.message || String(error);
    pista.style.color = "var(--r)";
  }
}
