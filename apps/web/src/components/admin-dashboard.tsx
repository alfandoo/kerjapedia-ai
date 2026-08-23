"use client";

import Link from "next/link";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck,
  ChevronRight,
  FileText,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
} from "lucide-react";
import { Toaster, toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { Callout, EmptyState, PageHeader, StatusBadge } from "@/components/admin/primitives";
import { cn } from "@/lib/utils";
import {
  createIngestionJob,
  fetchAdminOverview,
  updateAdminDocument,
  updateAdminPublication,
  updateAdminRelationships,
} from "@/lib/api";
import { fallbackAdminDocuments } from "@/lib/sample-data";
import type { AdminDocument, AdminRelationship } from "@/lib/types";

const ingestionLabels: Record<AdminDocument["ingestion_status"], string> = {
  completed: "Selesai",
  needs_review: "Perlu review",
  failed: "Gagal",
  running: "Berjalan",
  queued: "Antre",
};

type BadgeTone = "success" | "warning" | "danger" | "info" | "neutral";

const ingestionTone: Record<AdminDocument["ingestion_status"], BadgeTone> = {
  completed: "success",
  needs_review: "warning",
  failed: "danger",
  running: "info",
  queued: "neutral",
};

function formatDate(value: string) {
  return new Intl.DateTimeFormat("id-ID", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}

type InspectorProps = {
  document: AdminDocument;
  allDocuments: AdminDocument[];
  onChange: (document: AdminDocument) => void;
  onClose: () => void;
};

function DocumentInspector({ document, allDocuments, onChange, onClose }: InspectorProps) {
  const [activeTab, setActiveTab] = useState<"metadata" | "relasi" | "versi">("metadata");
  const [legalStatus, setLegalStatus] = useState(document.legal_status);
  const [verificationStatus, setVerificationStatus] = useState(document.verification_status);
  const [topics, setTopics] = useState(document.topics.join(", "));
  const [relationshipTarget, setRelationshipTarget] = useState(
    allDocuments.find((item) => item.document_id !== document.document_id)?.document_id ?? ""
  );

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
    } catch {
      toast.info("API belum tersedia — metadata disimpan lokal.");
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
    } catch {
      toast.info("API belum tersedia — perubahan disimpan lokal.");
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
    } catch {
      toast.info("API belum tersedia — relasi disimpan lokal.");
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
    } catch {
      toast.info("API belum tersedia — relasi dihapus lokal.");
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
    } catch {
      toast.info("API belum tersedia — status diperbarui lokal.");
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
    } catch {
      onChange({ ...document, ingestion_status: "queued" });
      toast.info("API belum tersedia — re-ingest masuk antrean lokal.");
    }
  }

  return (
    <>
      <SheetHeader className="border-b pb-4">
        <SheetDescription className="text-xs font-medium tracking-[0.16em] text-forest uppercase">
          Dokumen terpilih
        </SheetDescription>
        <SheetTitle className="text-lg">{document.short_title}</SheetTitle>
        <p className="font-mono text-xs text-muted-text">{document.document_id}</p>
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
                      <Trash2 className="text-[#a94442]" />
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

export function AdminDashboard() {
  const [documents, setDocuments] = useState(fallbackAdminDocuments);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [publicationFilter, setPublicationFilter] = useState("all");
  const [loadStatus, setLoadStatus] = useState("Memuat data admin...");
  const deferredSearch = useDeferredValue(search.toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminOverview(controller.signal)
      .then((overview) => {
        setDocuments(overview.documents);
        setLoadStatus("Data tersinkron dengan API.");
      })
      .catch(() => setLoadStatus("Menampilkan data contoh karena API belum tersedia."));
    return () => controller.abort();
  }, []);

  const filteredDocuments = useMemo(
    () =>
      documents.filter((document) => {
        const matchesSearch =
          `${document.short_title} ${document.title} ${document.topics.join(" ")}`
            .toLowerCase()
            .includes(deferredSearch);
        const matchesStatus = statusFilter === "all" || document.ingestion_status === statusFilter;
        const matchesPublication =
          publicationFilter === "all" || document.publication_status === publicationFilter;
        return matchesSearch && matchesStatus && matchesPublication;
      }),
    [deferredSearch, documents, publicationFilter, statusFilter]
  );

  const summary = useMemo(
    () => ({
      documents: documents.length,
      published: documents.filter((item) => item.publication_status === "published").length,
      needsReview: documents.filter((item) => item.ingestion_status === "needs_review").length,
      failed: documents.filter((item) => item.ingestion_status === "failed").length,
    }),
    [documents]
  );
  const selectedDocument = documents.find((item) => item.document_id === selectedId) ?? null;

  function replaceDocument(next: AdminDocument) {
    setDocuments((current) =>
      current.map((item) => (item.document_id === next.document_id ? next : item))
    );
  }

  const summaryCells = [
    {
      label: "Dokumen",
      value: summary.documents,
      note: "Total regulasi",
      dot: "bg-javanese/50",
      tone: "text-tinta",
    },
    {
      label: "Terbit",
      value: summary.published,
      note: "Sudah dipublikasikan",
      dot: "bg-forest",
      tone: "text-tinta",
    },
    {
      label: "Review",
      value: summary.needsReview,
      note: "Perlu ditinjau",
      dot: "bg-amber",
      tone: "text-amber",
    },
    {
      label: "Gagal",
      value: summary.failed,
      note: "Ingestion error",
      dot: "bg-red",
      tone: "text-red",
    },
  ];

  return (
    <div className="space-y-6">
      <Toaster position="bottom-right" richColors />

      <PageHeader
        eyebrow="Regulasi ketenagakerjaan"
        title="Knowledge Base"
        description={loadStatus}
        actions={
          <Button asChild className="bg-javanese text-white hover:bg-forest">
            <Link href="/admin/upload">
              <Upload /> Upload dokumen
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line lg:grid-cols-4">
        {summaryCells.map((cell) => (
          <div key={cell.label} className="flex flex-col gap-0.5 bg-white px-5 py-4">
            <p className="flex items-center gap-1.5 font-mono text-xl font-bold text-tinta tabular-nums">
              <span aria-hidden="true" className={cn("size-1.5 rounded-full", cell.dot)} />
              <span className={cell.tone}>{cell.value}</span>
            </p>
            <p className="text-sm font-medium">{cell.label}</p>
            <p className="text-xs text-muted-text">{cell.note}</p>
          </div>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Daftar dokumen</CardTitle>
          <CardDescription>
            Menampilkan {filteredDocuments.length} dari {documents.length} dokumen
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-48">
              <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-text" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Cari judul, topik..."
                className="pl-8"
              />
            </div>
            <Select value={statusFilter} onValueChange={setStatusFilter}>
              <SelectTrigger aria-label="Filter status ingestion">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua status</SelectItem>
                <SelectItem value="completed">Selesai</SelectItem>
                <SelectItem value="needs_review">Perlu review</SelectItem>
                <SelectItem value="failed">Gagal</SelectItem>
              </SelectContent>
            </Select>
            <Select value={publicationFilter} onValueChange={setPublicationFilter}>
              <SelectTrigger aria-label="Filter publikasi">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua publikasi</SelectItem>
                <SelectItem value="published">Terbit</SelectItem>
                <SelectItem value="draft">Draft</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dokumen</TableHead>
                <TableHead>Topik</TableHead>
                <TableHead>Ingestion</TableHead>
                <TableHead>Publikasi</TableHead>
                <TableHead>Versi</TableHead>
                <TableHead>Diperbarui</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {filteredDocuments.map((document) => (
                <TableRow
                  key={document.document_id}
                  className="cursor-pointer"
                  onClick={() => setSelectedId(document.document_id)}
                >
                  <TableCell className="max-w-64">
                    <span className="block truncate text-sm font-medium">
                      {document.short_title}
                    </span>
                    <span className="block text-xs text-muted-text">
                      {document.regulation_type} · {document.year}
                    </span>
                  </TableCell>
                  <TableCell>
                    {document.topics[0] ? (
                      <Badge variant="secondary">{document.topics[0].replaceAll("_", " ")}</Badge>
                    ) : (
                      <span className="text-xs text-muted-text">-</span>
                    )}
                  </TableCell>
                  <TableCell>
                    <StatusBadge
                      tone={ingestionTone[document.ingestion_status]}
                      pulse={document.ingestion_status === "running"}
                    >
                      {ingestionLabels[document.ingestion_status]}
                    </StatusBadge>
                  </TableCell>
                  <TableCell>
                    {document.publication_status === "published" ? (
                      <StatusBadge tone="success">Terbit</StatusBadge>
                    ) : (
                      <StatusBadge tone="neutral">Draft</StatusBadge>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-xs">v{document.version}</TableCell>
                  <TableCell className="text-xs">
                    <span className="block text-muted-text">{formatDate(document.updated_at)}</span>
                    <span className="block text-muted-text">oleh {document.updated_by}</span>
                  </TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      aria-label={`Edit ${document.short_title}`}
                      onClick={() => setSelectedId(document.document_id)}
                    >
                      <ChevronRight className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {filteredDocuments.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7}>
                    <EmptyState
                      icon={FileText}
                      title="Tidak ada dokumen yang cocok"
                      hint="Ubah kata kunci atau filter untuk melihat hasil lain."
                    />
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Sheet
        open={selectedDocument !== null}
        onOpenChange={(open) => {
          if (!open) setSelectedId(null);
        }}
      >
        <SheetContent side="right" className="w-full sm:max-w-md">
          {selectedDocument ? (
            <DocumentInspector
              key={selectedDocument.document_id}
              document={selectedDocument}
              allDocuments={documents}
              onChange={replaceDocument}
              onClose={() => setSelectedId(null)}
            />
          ) : null}
        </SheetContent>
      </Sheet>
    </div>
  );
}
