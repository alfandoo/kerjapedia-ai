import { ScaleIcon } from "@/components/icons";

export default function Loading() {
  return (
    <main
      className="grid min-h-screen place-items-center bg-background px-6 text-foreground"
      aria-busy="true"
      aria-live="polite"
    >
      <div className="flex flex-col items-center text-center">
        <div className="relative grid size-16 place-items-center rounded-2xl border border-javanese/20 bg-teal-soft text-javanese shadow-sm">
          <span className="absolute inset-[-5px] rounded-[1.15rem] border-2 border-javanese/20 border-t-javanese motion-safe:animate-spin" />
          <ScaleIcon className="size-7" />
        </div>
        <p className="mt-5 font-display text-xl font-medium text-javanese-deep">KerjaPedia AI</p>
        <p className="mt-1 text-sm text-muted-foreground">Menyiapkan halaman…</p>
        <span className="sr-only">Memuat halaman</span>
      </div>
    </main>
  );
}
