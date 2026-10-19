import type { Metadata, Viewport } from "next";
import { Instrument_Serif, Inter_Tight, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const sans = Inter_Tight({ variable: "--font-sans", subsets: ["latin"], weight: ["400", "500", "600", "800", "900"] });
const display = Instrument_Serif({ variable: "--font-display", subsets: ["latin"], weight: "400", style: ["normal", "italic"] });
const mono = JetBrains_Mono({ variable: "--font-mono", subsets: ["latin"], weight: ["400", "500"] });

export const metadata: Metadata = {
  title: "Image Privacy Toolkit — tu cara no es un dataset",
  description:
    "Herramientas gratuitas y locales para proteger tus fotos: limpia metadatos y oculta datos sensibles en tu navegador, busca posibles reutilizaciones y documenta evidencias, y añade una perturbación experimental contra modelos de imagen abiertos. Código abierto.",
};

export const viewport: Viewport = {
  themeColor: "#050608",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className={`${sans.variable} ${display.variable} ${mono.variable} grain antialiased`}>{children}</body>
    </html>
  );
}
