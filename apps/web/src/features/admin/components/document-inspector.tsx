"use client";

import detailStyles from "./document-detail.module.css";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ArrowLeft,
  BadgeCheck,
  Calendar,
  Check,
  FileText,
  Hash,
  History,
  Info,
  Link as LinkIcon,
  ListChecks,
  Plus,
  ShieldCheck,
  Trash2,
  Upload,
  WholeWord,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Callout, EmptyState, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import {
  clearStoredSession,
  updateAdminDocument,
  updateAdminPublication,
  updateAdminRelationships,
  verifyDocument,
} from "@/features/admin/api";
import type { AdminDocument, AdminRelationship } from "@/features/admin/types";

export const ingestionLabels: Record<AdminDocument["ingestion_status"], string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral";

export const ingestionTone: Record<AdminDocument["ingestion_status"], BadgeTone> = {
  completed: "success",
  needs_review: "warning",
  failed: "danger",
  running: "info",
  queued: "neutral",
};

function isAuthError(err: unknown): boolean {
  return /token|bearer/i.test((err as Error)?.message ?? "");
}

function describeError(err: unknown): string {
  const message = (err as Error)?.message ?? "";
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return "API tidak dapat dihubungi.";
  }
  return message || "Terjadi kesalahan tak terduga.";
}

export function formatDate(value: string) {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "Tidak diketahui";
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(d);
}

type InspectorProps = {
  document: AdminDocument;
  allDocuments: AdminDocument[];
  onChange: (document: AdminDocument) => void;
  onClose: () => void;
};

function isGoIdUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return (
      parsed.protocol === "https:" &&
      (parsed.hostname.endsWith(".go.id") || parsed.hostname === "go.id")
    );
  } catch {
    return false;
  }
}

type ChecklistItem = { done: boolean; label: string };

function ReadinessPanel({ items }: { items: ChecklistItem[] }) {
  const doneCount = items.filter((item) => item.done).length;
  const pct = Math.round((doneCount / items.length) * 100);
  return (
      <section aria-label="Kesiapan publikasi" className="rounded-xl border border-[#e5e5e5] bg-white">
      <div className="flex items-center justify-between gap-2 border-b border-[#e5e5e5] px-4 py-2.5">
        <p className="flex items-center gap-2 text-sm font-semibold text-tinta">
          <ListChecks aria-hidden="true" className="size-4 text-forest" />
          Kesiapan publikasi
        </p>
        <span
          className={cn(
            "font-mono text-xs font-semibold tabular-nums",
            doneCount === items.length ? "text-forest" : "text-muted-text"
          )}
        >
          {doneCount}/{items.length}
        </span>
      </div>
      <div className="space-y-3 px-4 py-3.5">
        <div className="h-1.5 overflow-hidden rounded-full bg-muted/40">
          <div
            className={cn(
              "h-full rounded-full transition-all",
              doneCount === items.length ? "bg-forest" : "bg-amber"
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
        <ul className="grid gap-x-4 gap-y-2 sm:grid-cols-2">
          {items.map((item) => (
            <li
              key={item.label}
              className={cn(
                "flex items-center gap-2 text-xs font-medium",
                item.done ? "text-forest" : "text-muted-text"
              )}
            >
              <span
                className={cn(
                  "flex size-4 shrink-0 items-center justify-center rounded-full",
                  item.done ? "bg-teal-soft" : "border border-[#e5e5e5] bg-muted/40"
                )}
              >
                {item.done ? (
                  <BadgeCheck className="size-3" />
                ) : (
                  <span className="size-1.5 rounded-full bg-muted-text/60" />
                )}
              </span>
              <span className="min-w-0 truncate">{item.label}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export function DocumentInspector({ document, allDocuments, onChange, onClose }: InspectorProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"metadata" | "relasi" | "versi">("metadata");
  const [legalStatus, setLegalStatus] = useState(document.legal_status);
  const [topics, setTopics] = useState(document.topics.join(", "));
  const [relationshipTarget, setRelationshipTarget] = useState(
    allDocuments.find((item) => item.document_id !== document.document_id)?.document_id ?? ""
  );
  const [relationshipType, setRelationshipType] =
    useState<AdminRelationship["relationship_type"]>("amended_by");
  const [sourceUrl, setSourceUrl] = useState(document.source_url);
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [republishing, setRepublishing] = useState(false);

  function handleAuthFailure(err: unknown): boolean {
    if (!isAuthError(err)) return false;
    clearStoredSession();
    router.push("/login-admin");
    return true;
  }

  async function saveMetadata() {
    const nextTopics = topics
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    const next = {
      ...document,
      legal_status: legalStatus,
      topics: nextTopics,
      source_url: sourceUrl,
    };
    onChange(next);
    setSaving(true);
    try {
      await updateAdminDocument(document.document_id, {
        legal_status: legalStatus,
        verification_status: document.verification_status,
        topics: nextTopics,
        source_url: sourceUrl,
      });
      toast.success("Metadata berhasil disimpan.");
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      toast.error(`Metadata gagal disimpan: ${describeError(err)}`);
    } finally {
      setSaving(false);
    }
  }

  const isDbVerified =
    document.source_verification_status === "verified" &&
    document.legal_review_status === "verified";

  const canPublish =
    document.ingestion_status === "completed" &&
    document.source_verification_status === "verified" &&
    document.legal_review_status === "verified" &&
    isGoIdUrl(document.source_url);

  async function markVerified() {
    if (!isGoIdUrl(sourceUrl)) {
      toast.error("URL sumber harus dari domain .go.id (pemerintah) sebelum verifikasi.");
      return;
    }
    onChange({
      ...document,
      legal_status: "active",
      verification_status: "verified",
      source_verification_status: "verified",
      legal_review_status: "verified",
      source_url: sourceUrl,
    });
    setLegalStatus("active");
    setVerifying(true);
    try {
      await updateAdminDocument(document.document_id, {
        legal_status: "active",
        verification_status: "verified",
        topics: Array.isArray(document.topics) ? document.topics : [],
        source_url: sourceUrl,
      });
      await verifyDocument(document.document_id, "source", "verified", sourceUrl);
      await verifyDocument(document.document_id, "legal", "verified", sourceUrl);
      toast.success("Dokumen ditandai terverifikasi.");
    } catch (err) {
      onChange(document);
      setLegalStatus(document.legal_status);
      if (handleAuthFailure(err)) return;
      toast.error(`Gagal menandai terverifikasi: ${describeError(err)}`);
    } finally {
      setVerifying(false);
    }
  }

  async function addRelationship() {
    if (!relationshipTarget) {
      toast.error("Pilih dokumen tujuan terlebih dahulu.");
      return;
    }
    const relationship: AdminRelationship = {
      from_document_id: document.document_id,
      to_document_id: relationshipTarget,
      relationship_type: relationshipType,
      confidence: "medium",
      notes: "Perlu verifikasi admin.",
    };
    const relationships = [...document.relationships, relationship];
    onChange({ ...document, relationships });
    try {
      await updateAdminRelationships(
        document.document_id,
        relationships.map((item) => ({
          to_document_id: item.to_document_id,
          relationship_type: item.relationship_type,
          confidence: item.confidence,
          notes: item.notes,
        }))
      );
      toast.success("Relasi berhasil diperbarui.");
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      toast.error(`Relasi gagal ditambahkan: ${describeError(err)}`);
    }
  }

  async function removeRelationship(relationship: AdminRelationship) {
    const relationships = document.relationships.filter((item) => item !== relationship);
    onChange({ ...document, relationships });
    try {
      await updateAdminRelationships(
        document.document_id,
        relationships.map((item) => ({
          to_document_id: item.to_document_id,
          relationship_type: item.relationship_type,
          confidence: item.confidence,
          notes: item.notes,
        }))
      );
      toast.success("Relasi berhasil dihapus.");
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      toast.error(`Relasi gagal dihapus: ${describeError(err)}`);
    }
  }

  async function changePublication() {
    const action = document.publication_status === "published" ? "unpublish" : "publish";
    const nextStatus = action === "publish" ? "published" : "draft";
    const nextVersion = document.version + 1;
    const next = {
      ...document,
      publication_status: nextStatus as AdminDocument["publication_status"],
      version: nextVersion,
      versions: [
        {
          version: nextVersion,
          status: nextStatus as "draft" | "published",
          created_at: new Date().toISOString(),
          created_by: "Admin",
        },
        ...document.versions,
      ],
    };
    onChange(next);
    setRepublishing(true);
    try {
      await updateAdminPublication(document.document_id, action);
      toast.success(action === "publish" ? "Dokumen diterbitkan." : "Penerbitan dibatalkan.");
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      const label =
        action === "publish" ? "Gagal menerbitkan dokumen" : "Gagal membatalkan penerbitan";
      toast.error(`${label}: ${describeError(err)}`);
    } finally {
      setRepublishing(false);
    }
  }

  const infoCells = [
    {
      icon: FileText,
      label: "Jenis",
      value: document.regulation_type,
    },
    { icon: Hash, label: "Nomor", value: document.number },
    { icon: Calendar, label: "Tahun", value: document.year },
    { icon: WholeWord, label: "Chunk", value: document.chunk_count },
  ];

  const readinessItems: ChecklistItem[] = [
    {
      done: document.ingestion_status === "completed",
      label:
        document.ingestion_status === "completed"
          ? "Ingestion selesai"
          : `Ingestion ${ingestionLabels[document.ingestion_status] ?? document.ingestion_status}`,
    },
    {
      done: document.source_verification_status === "verified",
      label:
        document.source_verification_status === "verified"
          ? "Sumber terverifikasi"
          : "Sumber belum terverifikasi",
    },
    {
      done: document.legal_review_status === "verified",
      label:
        document.legal_review_status === "verified"
          ? "Review hukum terverifikasi"
          : "Review hukum belum terverifikasi",
    },
    {
      done: isGoIdUrl(document.source_url),
      label: isGoIdUrl(document.source_url)
        ? "URL sumber dari .go.id"
        : "URL sumber belum dari .go.id",
    },
  ];

  return (
    <>
      <SheetHeader className="border-b px-5 pb-4">
        <SheetDescription className="text-[11px] font-semibold tracking-[0.18em] text-forest uppercase">
          Dokumen terpilih
        </SheetDescription>
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-teal-soft/70">
              <FileText aria-hidden="true" className="size-5 text-forest" />
            </span>
            <div className="min-w-0">
              <SheetTitle className="text-xl leading-snug">{document.short_title}</SheetTitle>
              <p className="mt-0.5 font-mono text-xs text-muted-text">{document.document_id}</p>
            </div>
          </div>
          <span className="shrink-0 rounded-lg bg-surface-soft px-2.5 py-1 font-mono text-xs font-semibold text-muted-text">
            v{document.version}
          </span>
        </div>
        <div className="flex flex-wrap gap-1.5 pt-1">
          <StatusBadge tone={ingestionTone[document.ingestion_status]}>
            {ingestionLabels[document.ingestion_status]}
          </StatusBadge>
          {isDbVerified ? (
            <StatusBadge tone="success">Verifikasi lengkap</StatusBadge>
          ) : (
            <StatusBadge tone="warning">Verifikasi belum lengkap</StatusBadge>
          )}
          {document.publication_status === "published" ? (
            <StatusBadge tone="success">Terbit</StatusBadge>
          ) : (
            <StatusBadge tone="neutral">Draft</StatusBadge>
          )}
        </div>
      </SheetHeader>

      <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
        <div className="grid grid-cols-2 gap-2">
          {infoCells.map((cell) => {
            const Icon = cell.icon;
            return (
              <div
                key={cell.label}
                className="rounded-lg border border-[#e5e5e5] bg-white px-3.5 py-2.5"
              >
                <p className="flex items-center gap-1.5 text-[11px] font-medium tracking-wide text-muted-text uppercase">
                  <Icon className="size-3.5" /> {cell.label}
                </p>
                <p className="mt-1 font-mono text-sm font-bold text-tinta tabular-nums">
                  {cell.value}
                </p>
              </div>
            );
          })}
        </div>

        <div className="rounded-xl border border-[#e5e5e5] bg-white p-3.5">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-tinta">
            <ShieldCheck className="size-4 text-forest" /> Verifikasi sistem
          </p>
          <div className="mt-2.5 flex flex-wrap items-center gap-2">
            <StatusBadge
              tone={document.source_verification_status === "verified" ? "success" : "warning"}
            >
              Sumber{" · "}
              {document.source_verification_status === "verified" ? "terverifikasi" : "belum"}
            </StatusBadge>
            <StatusBadge tone={document.legal_review_status === "verified" ? "success" : "warning"}>
              Hukum{" · "}
              {document.legal_review_status === "verified" ? "terverifikasi" : "belum"}
            </StatusBadge>
            {!isDbVerified ? (
              <Button
                variant="outline"
                size="sm"
                className="ml-auto"
                disabled={verifying}
                onClick={() => void markVerified()}
              >
                <BadgeCheck className="text-forest" />
                {verifying ? "Memverifikasi..." : "Tandai terverifikasi"}
              </Button>
            ) : null}
          </div>
        </div>

        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)}>
          <TabsList className="w-full bg-surface-soft">
            <TabsTrigger value="metadata" className="flex-1 gap-1.5">
              <Info aria-hidden="true" className="size-3.5" />
              Metadata
            </TabsTrigger>
            <TabsTrigger value="relasi" className="flex-1 gap-1.5">
              <LinkIcon aria-hidden="true" className="size-3.5" />
              Relasi
            </TabsTrigger>
            <TabsTrigger value="versi" className="flex-1 gap-1.5">
              <History aria-hidden="true" className="size-3.5" />
              Versi
            </TabsTrigger>
          </TabsList>

          <TabsContent value="metadata" className="mt-4 space-y-4">
            <div className="space-y-1.5">
              <Label>Judul singkat</Label>
              <Input value={document.short_title} readOnly />
            </div>

            <div className="space-y-1.5">
              <Label>Status hukum</Label>
              <Select value={legalStatus} onValueChange={setLegalStatus}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className={detailStyles.popup}>
                  <SelectItem value="active">Berlaku</SelectItem>
                  <SelectItem value="needs_verification">Perlu verifikasi</SelectItem>
                  <SelectItem value="historical">Historis</SelectItem>
                  <SelectItem value="revoked">Dicabut</SelectItem>
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-text">
                Dokumen dengan status selain Berlaku tidak diikutkan pada retrieval publik.
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>URL sumber (source URL)</Label>
              <Input
                placeholder="https://peraturan.go.id/..."
                value={sourceUrl}
                onChange={(event) => setSourceUrl(event.target.value)}
              />
              {!isGoIdUrl(sourceUrl) ? (
                <p className="text-xs text-red">
                  URL harus dari domain .go.id (pemerintah) untuk dapat diverifikasi dan
                  diterbitkan.
                </p>
              ) : (
                <p className="text-xs text-forest">URL valid dari domain pemerintah.</p>
              )}
            </div>

            <div className="space-y-1.5">
              <Label>Topik (pisahkan dengan koma)</Label>
              <Textarea
                value={topics}
                onChange={(event) => setTopics(event.target.value)}
                rows={3}
              />
            </div>

            <Button
              className="w-full bg-javanese text-white hover:bg-forest"
              disabled={saving}
              onClick={() => void saveMetadata()}
            >
              <Check aria-hidden="true" />
              {saving ? "Menyimpan..." : "Simpan perubahan"}
            </Button>
          </TabsContent>

          <TabsContent value="relasi" className="mt-4">
            <div className="space-y-4">
              {document.relationships.length ? (
                <ul className="space-y-2">
                  {document.relationships.map((relationship) => {
                    const target = allDocuments.find(
                      (item) => item.document_id === relationship.to_document_id
                    );
                    const relTypeLabel =
                      relationship.relationship_type === "amended_by"
                        ? "Diubah oleh"
                        : relationship.relationship_type === "implements"
                          ? "Mengimplementasikan"
                          : relationship.relationship_type === "implemented_by"
                            ? "Diimplementasikan oleh"
                            : relationship.relationship_type === "related_to"
                              ? "Terkait dengan"
                              : String(relationship.relationship_type).replaceAll("_", " ");
                    return (
                      <li
                        key={`${relationship.relationship_type}-${relationship.to_document_id}`}
                        className="group flex items-center gap-3 rounded-lg border border-[#e5e5e5] bg-white px-3 py-2.5"
                      >
                        <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-surface-soft text-muted-text">
                          <LinkIcon className="size-4" />
                        </span>
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-sm font-medium text-tinta">
                            {target?.short_title ?? relationship.to_document_id}
                          </p>
                          <p className="flex items-center gap-1.5 font-mono text-[11px] text-muted-text">
                            <span className="truncate">{relTypeLabel}</span>
                            <span aria-hidden="true" className="text-muted-text/40">
                              ·
                            </span>
                            <span className="truncate">{relationship.to_document_id}</span>
                          </p>
                        </div>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          aria-label={`Hapus relasi ${relationship.to_document_id}`}
                          onClick={() => void removeRelationship(relationship)}
                        >
                          <Trash2 className="text-red" />
                        </Button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <EmptyState
                  icon={LinkIcon}
                  title="Belum ada relasi hukum"
                  hint="Tambahkan hubungan antar-regulasi seperti 'diubah oleh' atau 'mengimplementasikan'."
                />
              )}

              <div className="rounded-xl border border-[#e5e5e5] bg-white p-3.5">
                <p className="text-sm font-semibold text-tinta">Tambah hubungan</p>
                <div className="mt-3 space-y-3">
                  <div className="space-y-1.5">
                    <Label>Jenis hubungan</Label>
                    <div className="flex flex-wrap gap-2">
                      <button
                        type="button"
                        onClick={() => setRelationshipType("amended_by")}
                        className={cn(
                          "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                          relationshipType === "amended_by"
                            ? "border-javanese bg-javanese text-white"
                            : "border-[#e5e5e5] bg-white text-muted-text hover:border-javanese/40 hover:text-tinta"
                        )}
                      >
                        Diubah oleh
                      </button>
                      <button
                        type="button"
                        onClick={() => setRelationshipType("implements")}
                        className={cn(
                          "rounded-lg border px-3 py-1.5 text-xs font-medium transition-colors",
                          relationshipType === "implements"
                            ? "border-javanese bg-javanese text-white"
                            : "border-[#e5e5e5] bg-white text-muted-text hover:border-javanese/40 hover:text-tinta"
                        )}
                      >
                        Mengimplementasikan
                      </button>
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label>Dokumen tujuan</Label>
                    <Select value={relationshipTarget} onValueChange={setRelationshipTarget}>
                      <SelectTrigger className="w-full">
                        <SelectValue placeholder="Pilih dokumen" />
                      </SelectTrigger>
                      <SelectContent className={detailStyles.popup}>
                        {allDocuments
                          .filter((item) => item.document_id !== document.document_id)
                          .map((item) => (
                            <SelectItem key={item.document_id} value={item.document_id}>
                              {item.short_title}
                            </SelectItem>
                          ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <Button
                    className="w-full bg-javanese text-white hover:bg-forest"
                    disabled={!relationshipTarget}
                    onClick={() => void addRelationship()}
                  >
                    <Plus /> Tambah hubungan
                  </Button>
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="versi" className="mt-4">
            <div className="relative pl-5">
              <span
                aria-hidden="true"
                className="absolute top-1.5 bottom-1.5 left-[7px] w-px bg-[#e5e5e5]"
              />
              <ul className="space-y-3">
                {document.versions.map((version) => {
                  const isCurrent = version.version === document.version;
                  return (
                    <li key={`${version.version}-${version.created_at}`} className="relative">
                      <span
                        aria-hidden="true"
                        className={cn(
                          "absolute top-1 -left-[18px] flex size-3.5 items-center justify-center rounded-full border-2 bg-white",
                          isCurrent ? "border-forest" : "border-[#e5e5e5]"
                        )}
                      >
                        {isCurrent ? <span className="size-1.5 rounded-full bg-forest" /> : null}
                      </span>
                      <div
                        className={cn(
                          "flex items-start justify-between gap-3 rounded-lg border px-3 py-2.5",
                          isCurrent ? "border-forest/20 bg-teal-soft/40" : "border-[#e5e5e5] bg-white"
                        )}
                      >
                        <div className="min-w-0 flex-1">
                          <p className="flex items-center gap-2">
                            <span className="font-mono text-sm font-semibold">
                              v{version.version}
                            </span>
                            {version.status === "published" ? (
                              <StatusBadge tone="success">Terbit</StatusBadge>
                            ) : (
                              <StatusBadge tone="neutral">Draft</StatusBadge>
                            )}
                            {isCurrent ? <StatusBadge tone="info">Aktif</StatusBadge> : null}
                          </p>
                          <p className="mt-1 text-xs text-muted-text">
                            {formatDate(version.created_at)}
                            {" · "}oleh {version.created_by}
                          </p>
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          </TabsContent>
        </Tabs>

        <ReadinessPanel items={readinessItems} />

        {document.last_error ? (
          <Callout tone="warning" title="Log parsing perlu ditinjau">
            {document.last_error}
          </Callout>
        ) : (
          <Callout tone="success" title="Parsing tanpa error">
            {document.chunk_count} chunk siap digunakan.
          </Callout>
        )}
      </div>

      <SheetFooter className="border-t bg-white px-5 py-4">
        <Button
          className="w-full bg-javanese text-white hover:bg-forest"
          disabled={!canPublish || republishing}
          onClick={() => void changePublication()}
        >
          <Upload aria-hidden="true" />
          {republishing
            ? "Memproses..."
            : document.publication_status === "published"
              ? "Batalkan terbit"
              : "Terbitkan"}
        </Button>
        <Button variant="ghost" className="w-full text-muted-text" onClick={onClose}>
          <ArrowLeft aria-hidden="true" />
          Kembali ke daftar
        </Button>
      </SheetFooter>
    </>
  );
}
