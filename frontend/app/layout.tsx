import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";
import { cn } from "@/lib/utils";
import { Providers } from "@/app/providers";
import { AppSidebar } from "@/components/app-sidebar";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans" });

const jetbrainsMono = JetBrains_Mono({
  subsets: ["latin"],
  variable: "--font-jetbrains-mono",
});

export const metadata: Metadata = {
  title: "Research tracker",
  description: "Experiments and CEBRA runs on IBL data",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={cn("h-full antialiased font-sans", inter.variable, jetbrainsMono.variable)}
    >
      <body className="min-h-full bg-zinc-50 text-sm text-zinc-950">
        <Providers>
          <div className="flex min-h-screen flex-col md:flex-row">
            <AppSidebar />
            <main className="min-w-0 flex-1">
              <div className="mx-auto w-full max-w-[1080px] px-4 py-7 md:px-10">
                {children}
              </div>
            </main>
          </div>
        </Providers>
      </body>
    </html>
  );
}
