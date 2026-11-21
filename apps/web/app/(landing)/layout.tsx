import { SiteHeader } from "@/components/site/site-header";

// Landing pública y login: la barra superior va sin menú, la demo vive en /demo detrás del login
export default function LandingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-dvh flex-col">
      <SiteHeader nav={false} />
      <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-6 sm:px-6">{children}</main>
      <footer className="border-t px-4 py-4 text-center text-xs text-muted-foreground">AIgis</footer>
    </div>
  );
}
