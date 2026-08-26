// Copie este archivo como `firebase-config.js` y complete los valores del
// proyecto (Consola de Firebase → Configuración del proyecto → Tus apps).
//
// Sin `firebase-config.js` el informe funciona igual, en modo autónomo: se ve
// el curso de ejemplo y el Paso 1 queda como maqueta. Es lo que permite
// abrir el .html suelto, sin servidor (guía §1).
export const firebaseConfig = {
  apiKey: "…",
  authDomain: "jumpmath-dia.firebaseapp.com",
  projectId: "jumpmath-dia",
  storageBucket: "jumpmath-dia.appspot.com",
  messagingSenderId: "…",
  appId: "…",
};

// Región de las Cloud Functions (debe coincidir con functions/main.py).
export const region = "southamerica-west1";

// Clave pública de reCAPTCHA v3 para App Check. Deje `null` para desactivarlo.
export const appCheckSiteKey = null;
