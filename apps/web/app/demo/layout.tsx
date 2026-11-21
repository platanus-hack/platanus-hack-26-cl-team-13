import { SiteHeader } from "@/components/site/site-header";

export default function SiteLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader />
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">{children}</main>
      <footer className="border-t px-4 py-4 text-center text-xs text-muted-foreground">
        AIgis · Equipo 13 · Platanus Hack 26 · Track AI Security
      </footer>
    </div>
  );
}
