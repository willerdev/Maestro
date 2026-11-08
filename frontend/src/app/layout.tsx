import type { Metadata } from "next";
import { BusyRoot } from "@/components/BusyRoot";
import "./globals.css";

export const metadata: Metadata = {
  title: "Maestro",
  description: "Multi-account MT5 risk desk",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" data-theme="light" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap" rel="stylesheet" />
        <script
          dangerouslySetInnerHTML={{
            __html: `try{var stored=localStorage.getItem('tg-theme');var theme=stored==='dark'||stored==='light'?stored:(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light');document.documentElement.dataset.theme=theme;}catch(e){}`,
          }}
        />
      </head>
      <body>
        <BusyRoot />
        {children}
      </body>
    </html>
  );
}
