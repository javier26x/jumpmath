// Configuración del proyecto Firebase `jumpmathv2`.
//
// Estos valores son públicos por diseño: viajan al navegador en cualquier app
// web de Firebase y sirven para *identificar* el proyecto, no para autorizar.
// Lo que protege los datos son las reglas de Firestore y de Storage —que
// acotan cada docente a su propio `uid`— y, si se activa, App Check. Por eso
// el archivo se versiona.
//
// La clave que sí es secreta es la de la cuenta de servicio del backend, y
// esa no vive aquí: las Cloud Functions la obtienen del entorno.
export const firebaseConfig = {
  apiKey: "AIzaSyDtsPOHrzokutM_Efhn4pM5pMBljcg6oC8",
  authDomain: "jumpmathv2.firebaseapp.com",
  projectId: "jumpmathv2",
  storageBucket: "jumpmathv2.firebasestorage.app",
  messagingSenderId: "327183766661",
  appId: "1:327183766661:web:bd45e32c1792af187845ec",
};

// Región de las Cloud Functions. Debe coincidir con `REGION` en
// functions/main.py: si no, las llamadas fallan con NOT_FOUND.
export const region = "us-east1";

// Clave pública de reCAPTCHA v3 para App Check. Se obtiene en la consola de
// Firebase → App Check → Apps → reCAPTCHA v3. Con `null` queda desactivado.
export const appCheckSiteKey = null;
