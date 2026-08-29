"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { BadgeCheck, Plus, RefreshCw, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Badge } from "@/components/ui/badge";
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
import { Callout, StatusBadge } from "./primitives";
import {
  clearStoredSession,
  createIngestionJob,
  updateAdminDocument,
  updateAdminPublication,
  updateAdminRelationships,
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

const PAGE_SIZE = 10;

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
  if (Number.isNaN(d.getTime())) return "—";
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

export function DocumentInspector({ document, allDocuments, onChange, onClose }: InspectorProps) {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<"metadata" | "relasi" | "versi">("metadata");
  const [legalStatus, setLegalStatus] = useState(document.legal_status);
  const [verificationStatus, setVerificationStatus] = useState(document.verification_status);
  const [topics, setTopics] = useState(document.topics.join(", "));
  const [relationshipTarget, setRelationshipTarget] = useState(
    allDocuments.find((item) => item.document_id !== document.document_id)?.document_id ?? ""
  );

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
      verification_status: verificationStatus,
      topics: nextTopics,
    };
    onChange(next);
    try {
      await updateAdminDocument(document.document_id, {
        legal_status: legalStatus,
        verification_status: verificationStatus,
        topics: nextTopics,
      });
      toast.success("Metadata berhasil disimpan.");
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      toast.error(`Metadata gagal disimpan: ${describeError(err)}`);
    }
  }

  const isVerified =
    document.legal_status === "active" && document.verification_status === "verified";

  async function markVerified() {
    onChange({
      ...document,
      legal_status: "active",
      verification_status: "verified",
    });
    setLegalStatus("active");
    setVerificationStatus("verified");
    try {
      await updateAdminDocument(document.document_id, {
        legal_status: "active",
        verification_status: "verified",
        topics: Array.isArray(document.topics) ? document.topics : [],
      });
      toast.success("Dokumen ditandai terverifikasi.");
    } catch (err) {
      onChange(document);
      setLegalStatus(document.legal_status);
      setVerificationStatus(document.verification_status);
      if (handleAuthFailure(err)) return;
      toast.error(`Gagal menandai terverifikasi: ${describeError(err)}`);
    }
  }

  async function addRelationship() {
    if (!relationshipTarget) return;
    const relationship: AdminRelationship = {
      from_document_id: document.document_id,
      to_document_id: relationshipTarget,
      relationship_type: "amended_by",
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
    try {
      await updateAdminPublication(document.document_id, action);
      toast.success(action === "publish" ? "Dokumen diterbitkan." : "Penerbitan dibatalkan.");
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      const label =
        action === "publish" ? "Gagal menerbitkan dokumen" : "Gagal membatalkan penerbitan";
      toast.error(`${label}: ${describeError(err)}`);
    }
  }

  async function reingest() {
    onChange({ ...document, ingestion_status: "running" });
    try {
      const job = await createIngestionJob(document.document_id);
      onChange({ ...document, ingestion_status: job.status });
      toast.success(
        `Re-ingest selesai dengan status ${ingestionLabels[job.status] ?? job.status}.`
      );
    } catch (err) {
      onChange(document);
      if (handleAuthFailure(err)) return;
      toast.error(`Re-ingest gagal dijalankan: ${describeError(err)}`);
    }
  }

  return (
    <>
      <SheetHeader className="border-b pb-4">
        <SheetDescription className="text-xs font-medium tracking-[0.16em] text-forest uppercase">
          Dokumen terpilih
        </SheetDescription>
        <SheetTitle className="text-lg leading-snug">{document.short_title}</SheetTitle>
        <p className="font-mono text-xs text-muted-text">{document.document_id}</p>
        <div className="flex flex-wrap gap-1.5 pt-1.5">
          <StatusBadge tone={ingestionTone[document.ingestion_status]}>
            {ingestionLabels[document.ingestion_status]}
          </StatusBadge>
          {document.publication_status === "published" ? (
            <StatusBadge tone="success">Terbit</StatusBadge>
          ) : (
            <StatusBadge tone="neutral">Draft</StatusBadge>
          )}
          <StatusBadge tone="neutral">v{document.version}</StatusBadge>
        </div>
      </SheetHeader>

      <div className="flex-1 overflow-y-auto px-4">
        <Tabs value={activeTab} onValueChange={(value) => setActiveTab(value as typeof activeTab)}>
          <TabsList className="w-full">
            <TabsTrigger value="metadata" className="flex-1">
              Metadata
            </TabsTrigger>
            <TabsTrigger value="relasi" className="flex-1">
              Relasi
            </TabsTrigger>
            <TabsTrigger value="versi" className="flex-1">
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
                <SelectContent>
                  <SelectItem value="active">Berlaku</SelectItem>
                  <SelectItem value="needs_verification">Perlu verifikasi</SelectItem>
                  <SelectItem value="historical">Historis</SelectItem>
                  <SelectItem value="revoked">Dicabut</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label>Status verifikasi</Label>
              <Select value={verificationStatus} onValueChange={setVerificationStatus}>
                <SelectTrigger className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="verified">Terverifikasi</SelectItem>
                  <SelectItem value="pending_detail_url">Menunggu URL detail</SelectItem>
                  <SelectItem value="needs_review">Perlu review</SelectItem>
                </SelectContent>
              </Select>
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
              onClick={() => void saveMetadata()}
            >
              Simpan perubahan
            </Button>
            {!isVerified ? (
              <div className="space-y-1.5">
                <Button variant="outline" className="w-full" onClick={() => void markVerified()}>
                  <BadgeCheck className="text-forest" /> Tandai terverifikasi
                </Button>
                <p className="text-xs text-muted-text">
                  Tetapkan sekaligus sebagai Berlaku + Terverifikasi.
                </p>
              </div>
            ) : (
              <p className="flex items-center gap-1.5 text-xs text-forest">
                <BadgeCheck className="size-3.5" /> Dokumen sudah terverifikasi
              </p>
            )}
          </TabsContent>

          <TabsContent value="relasi" className="mt-4 space-y-4">
            {document.relationships.length ? (
              <ul className="space-y-2">
                {document.relationships.map((relationship) => (
                  <li
                    key={`${relationship.relationship_type}-${relationship.to_document_id}`}
                    className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2.5"
                  >
                    <div className="min-w-0">
                      <Badge variant="secondary" className="mb-1">
                        {relationship.relationship_type.replaceAll("_", " ")}
                      </Badge>
                      <p className="truncate font-mono text-xs text-muted-text">
                        {relationship.to_document_id}
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
                ))}
              </ul>
            ) : (
              <p className="rounded-lg bg-surface-soft px-3 py-4 text-sm text-muted-text">
                Belum ada relasi hukum untuk dokumen ini.
              </p>
            )}
            <div className="space-y-1.5">
              <Label>Tambah relasi &quot;diubah oleh&quot;</Label>
              <Select value={relationshipTarget} onValueChange={setRelationshipTarget}>
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Pilih dokumen" />
                </SelectTrigger>
                <SelectContent>
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
            <Button variant="outline" className="w-full" onClick={() => void addRelationship()}>
              <Plus /> Tambah relasi
            </Button>
          </TabsContent>

          <TabsContent value="versi" className="mt-4">
            <ul className="space-y-2">
              {document.versions.map((version) => (
                <li
                  key={`${version.version}-${version.created_at}`}
                  className="flex items-center justify-between gap-3 rounded-lg border border-line px-3 py-2.5"
                >
                  <span className="font-mono text-sm font-semibold">v{version.version}</span>
                  <span className="flex-1">
                    <strong className="block text-sm">
                      {version.status === "published" ? "Terbit" : "Draft"}
                    </strong>
                    <small className="text-xs text-muted-text">
                      {formatDate(version.created_at)} oleh {version.created_by}
                    </small>
                  </span>
                  {version.version === document.version ? (
                    <StatusBadge tone="success">Aktif</StatusBadge>
                  ) : null}
                </li>
              ))}
            </ul>
          </TabsContent>
        </Tabs>

        <div className="mt-4">
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
      </div>

      <SheetFooter className="border-t pt-4">
        <div className="grid grid-cols-2 gap-2">
          <Button variant="outline" onClick={() => void reingest()}>
            <RefreshCw /> Re-ingest
          </Button>
          <Button
            className="bg-javanese text-white hover:bg-forest"
            onClick={() => void changePublication()}
          >
            {document.publication_status === "published" ? "Batalkan terbit" : "Terbitkan"}
          </Button>
        </div>
        <Button variant="ghost" onClick={onClose}>
          Tutup editor
        </Button>
      </SheetFooter>
    </>
  );
}
