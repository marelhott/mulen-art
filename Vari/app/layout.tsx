import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Variants",
  description: "Generate artistic variations from a source image",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
    apple: "/favicon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="cs">
      <body className="cursor-shell">{children}</body>
    </html>
  );
}
