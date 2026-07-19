import { AppShell } from "@/components/app-shell";
import { RegulationSearch } from "@/components/regulation-search";
import { SourcePanel } from "@/components/source-panel";

export default function SearchPage() {
  return (
    <AppShell rightPanel={<SourcePanel />}>
      <RegulationSearch />
    </AppShell>
  );
}
