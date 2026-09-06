import type { Metadata } from "next";
import { cookies, headers } from "next/headers";
import { parseTheme } from "@/features/settings/theme";
import { parseLanguage, resolveLanguage } from "@/features/settings/language";
import { SessionBootstrap } from "@/features/auth/components/session-bootstrap";
import { Inter, JetBrains_Mono, Playfair_Display } from "next/font/google";
import "./globals.css";
import { SettingsProvider } from "@/features/settings";

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const jetbrainsMono = JetBrains_Mono({
  variable: "--font-jetbrains-mono",
  subsets: ["latin"],
});

const playfairDisplay = Playfair_Display({
  variable: "--font-playfair",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "KerjaPedia AI",
  description: "Asisten regulasi ketenagakerjaan Indonesia berbasis RAG.",
  icons: {
    icon: "/icon.svg",
  },
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const requestHeaders = await headers();
  const nonce = requestHeaders.get("x-nonce") ?? undefined;
  const preferences = await cookies();
  const savedLanguage = parseLanguage(preferences.get("settings-language")?.value);
  const savedTheme = parseTheme(preferences.get("settings-theme")?.value);
  const initialTheme = savedTheme ?? "system";
  const initialResolvedTheme = initialTheme === "dark" ? "dark" : "light";
  const initialLanguage = savedLanguage ?? "auto";
  const initialResolvedLanguage = resolveLanguage(
    initialLanguage,
    requestHeaders.get("accept-language") ?? "id"
  );
  return (
    <html
      lang={initialResolvedLanguage}
      data-theme={initialResolvedTheme}
      style={{ colorScheme: initialResolvedTheme }}
      suppressHydrationWarning
      className={`${inter.variable} ${jetbrainsMono.variable} ${playfairDisplay.variable} h-full antialiased ${initialResolvedTheme}`}
    >
      <head>
        <script
          nonce={nonce}
          suppressHydrationWarning
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var t=${JSON.stringify(initialTheme)};var d=t==="dark"||(t!=="light"&&matchMedia("(prefers-color-scheme: dark)").matches);var r=document.documentElement;r.classList.toggle("dark",d);r.classList.toggle("light",!d);r.style.colorScheme=d?"dark":"light";r.dataset.theme=d?"dark":"light"}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-full flex flex-col">
        <SettingsProvider
          initialLanguage={initialLanguage}
          initialResolvedLanguage={initialResolvedLanguage}
          initialTheme={initialTheme}
        >
          <SessionBootstrap />
          {children}
        </SettingsProvider>
      </body>
    </html>
  );
}
