import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Salida autocontenida para la imagen de Docker.
  output: "standalone",
  // Fija la raíz del rastreo de archivos a esta app. Sin esto, Next puede
  // inferir mal la raíz si hay otros package-lock.json en carpetas superiores
  // (p. ej. en el HOME), y empaquetar archivos equivocados en `standalone`.
  outputFileTracingRoot: path.join(__dirname),
};

export default nextConfig;
