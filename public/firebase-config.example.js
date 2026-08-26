// Plantilla de `firebase-config.js`, por si hay que apuntar a otro proyecto
// (por ejemplo uno de pruebas). Los valores se copian de la consola de
// Firebase → Configuración del proyecto → Tus apps.
//
// Sin `firebase-config.js` el informe funciona igual, en modo autónomo: se ve
// el curso de ejemplo y el Paso 1 queda como maqueta. Es lo que permite abrir
// el .html suelto, sin servidor (guía §1).
export const firebaseConfig = {
  apiKey: "…",
  authDomain: "PROYECTO.firebaseapp.com",
  projectId: "PROYECTO",
  storageBucket: "PROYECTO.firebasestorage.app",
  messagingSenderId: "…",
  appId: "…",
};

// Debe coincidir con `REGION` en functions/main.py.
export const region = "southamerica-west1";

// Clave pública de reCAPTCHA v3 para App Check. `null` lo desactiva.
export const appCheckSiteKey = null;
