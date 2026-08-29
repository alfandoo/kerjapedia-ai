"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDeferredValue, useEffect, useMemo, useState } from "react";
import {
  BadgeCheck,
  ChevronLeft,
  ChevronRight,
  FileText,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  Upload,
  X,
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
import { Callout, EmptyState, PageHeader, StatusBadge } from "./primitives";
import { cn } from "@/lib/utils";
import {
  clearStoredSession,
  createIngestionJob,
  fetchAdminOverview,
  updateAdminDocument,
  updateAdminPublication,
  updateAdminRelationships,
} from "@/features/admin/api";
import { fallbackAdminDocuments } from "@/features/admin/sample-data";
import type { AdminDocument, AdminRelationship } from "@/features/admin/types";

import {
  DocumentInspector,
  formatDate,
  ingestionLabels,
  ingestionTone,
} from "./document-inspector";

const PAGE_SIZE = 10;

export function AdminDashboard() {
  const router = useRouter();
  const [documents, setDocuments] = useState(fallbackAdminDocuments);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [publicationFilter, setPublicationFilter] = useState("all");
  const [page, setPage] = useState(1);
  const [loadStatus, setLoadStatus] = useState("Memuat data admin...");
  const deferredSearch = useDeferredValue(search.toLowerCase());

  useEffect(() => {
    const controller = new AbortController();
    fetchAdminOverview(controller.signal)
      .then((overview) => {
        setDocuments(overview.documents);
        setLoadStatus("Data tersinkron dengan API.");
      })
      .catch((err) => {
        if ((err as Error).name === "AbortError") return;
        const message = (err as Error).message || "";
        if (/token|bearer/i.test(message)) {
          clearStoredSession();
          router.push("/login-admin");
          return;
        }
        setLoadStatus("API tidak dapat dihubungi — menampilkan data contoh.");
      });
    return () => controller.abort();
  }, [router]);

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

  const totalPages = Math.max(1, Math.ceil(filteredDocuments.length / PAGE_SIZE));
  const safePage = Math.min(page, totalPages);
  const pagedDocuments = filteredDocuments.slice((safePage - 1) * PAGE_SIZE, safePage * PAGE_SIZE);
  const rangeStart = filteredDocuments.length === 0 ? 0 : (safePage - 1) * PAGE_SIZE + 1;
  const rangeEnd = Math.min(safePage * PAGE_SIZE, filteredDocuments.length);

  function goToPage(next: number) {
    setPage(Math.min(Math.max(1, next), totalPages));
  }

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
        description="Kelola dokumen regulasi yang menjadi sumber jawaban KerjaPedia AI."
        actions={
          <Button
            asChild
            className="h-11 bg-javanese px-5 text-sm font-bold text-white shadow-[0_2px_12px_rgba(27,67,50,0.22)] hover:bg-javanese-deep"
          >
            <Link href="/admin/upload">
              <Upload strokeWidth={2} /> Upload dokumen
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-px overflow-hidden rounded-xl border border-line bg-line lg:grid-cols-4">
        {summaryCells.map((cell) => {
          const actionable =
            (cell.label === "Review" && summary.needsReview > 0) ||
            (cell.label === "Gagal" && summary.failed > 0);
          return (
            <button
              key={cell.label}
              type="button"
              disabled={!actionable}
              onClick={() => {
                setStatusFilter(cell.label === "Gagal" ? "failed" : "needs_review");
                setPublicationFilter("all");
                setPage(1);
              }}
              className={cn(
                "flex flex-col items-start gap-0.5 bg-white px-5 py-4 text-left",
                actionable ? "transition-colors hover:bg-surface-soft" : "cursor-default"
              )}
            >
              <p className="flex items-center gap-1.5 font-mono text-xl font-bold text-tinta tabular-nums">
                <span aria-hidden="true" className={cn("size-1.5 rounded-full", cell.dot)} />
                <span className={cell.tone}>{cell.value}</span>
              </p>
              <p className="text-sm font-medium">{cell.label}</p>
              <p className="text-xs text-muted-text">{cell.note}</p>
            </button>
          );
        })}
      </div>

      <Card>
        <CardHeader className="flex flex-row items-start justify-between space-y-0">
          <div className="space-y-1.5">
            <CardTitle>Daftar dokumen</CardTitle>
            <CardDescription>
              Menampilkan {filteredDocuments.length} dari {documents.length} dokumen
            </CardDescription>
          </div>
          <StatusBadge
            tone={loadStatus.startsWith("Data tersinkron") ? "info" : "neutral"}
            pulse={!loadStatus.startsWith("Data tersinkron")}
          >
            {loadStatus}
          </StatusBadge>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-56 flex-1">
              <Search className="absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-text" />
              <Input
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setPage(1);
                }}
                placeholder="Cari judul, nomor, topik..."
                aria-label="Cari dokumen"
                className="pl-8"
              />
            </div>
            <Select
              value={statusFilter}
              onValueChange={(value) => {
                setStatusFilter(value);
                setPage(1);
              }}
            >
              <SelectTrigger aria-label="Filter status ingestion" className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua status</SelectItem>
                <SelectItem value="completed">Selesai</SelectItem>
                <SelectItem value="needs_review">Perlu review</SelectItem>
                <SelectItem value="failed">Gagal</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={publicationFilter}
              onValueChange={(value) => {
                setPublicationFilter(value);
                setPage(1);
              }}
            >
              <SelectTrigger aria-label="Filter publikasi" className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Semua publikasi</SelectItem>
                <SelectItem value="published">Terbit</SelectItem>
                <SelectItem value="draft">Draft</SelectItem>
              </SelectContent>
            </Select>
            {search || statusFilter !== "all" || publicationFilter !== "all" ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => {
                  setSearch("");
                  setStatusFilter("all");
                  setPublicationFilter("all");
                  setPage(1);
                }}
              >
                <X /> Reset
              </Button>
            ) : null}
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
              {pagedDocuments.map((document) => (
                <TableRow
                  key={document.document_id}
                  className="group cursor-pointer"
                  onClick={() => setSelectedId(document.document_id)}
                >
                  <TableCell className="max-w-64">
                    <span className="block truncate text-sm font-medium group-hover:text-javanese">
                      {document.short_title}
                    </span>
                    <span className="block font-mono text-xs text-muted-text">
                      {document.regulation_type} · {document.year}
                    </span>
                  </TableCell>
                  <TableCell>
                    {document.topics[0] ? (
                      <span className="flex items-center gap-1.5">
                        <Badge variant="secondary">{document.topics[0].replaceAll("_", " ")}</Badge>
                        {document.topics.length > 1 ? (
                          <span className="text-xs text-muted-text">
                            +{document.topics.length - 1}
                          </span>
                        ) : null}
                      </span>
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
                      className="opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                      onClick={(event) => {
                        event.stopPropagation();
                        setSelectedId(document.document_id);
                      }}
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
                      action={
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setSearch("");
                            setStatusFilter("all");
                            setPublicationFilter("all");
                            setPage(1);
                          }}
                        >
                          <X /> Reset filter
                        </Button>
                      }
                    />
                  </TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>

          {filteredDocuments.length > 0 ? (
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
              <p className="text-xs text-muted-text tabular-nums">
                Menampilkan {rangeStart}–{rangeEnd} dari {filteredDocuments.length} dokumen
              </p>
              {totalPages > 1 ? (
                <nav aria-label="Navigasi halaman" className="flex items-center gap-1">
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    disabled={safePage === 1}
                    aria-label="Halaman sebelumnya"
                    onClick={() => goToPage(safePage - 1)}
                  >
                    <ChevronLeft className="size-4" />
                  </Button>
                  {Array.from({ length: totalPages }, (_, index) => index + 1).map((pageNumber) => (
                    <button
                      key={pageNumber}
                      type="button"
                      aria-current={pageNumber === safePage ? "page" : undefined}
                      onClick={() => goToPage(pageNumber)}
                      className={cn(
                        "flex size-8 items-center justify-center rounded-lg font-mono text-xs font-semibold transition-colors",
                        pageNumber === safePage
                          ? "bg-javanese text-white"
                          : "text-muted-text hover:bg-surface-soft hover:text-tinta"
                      )}
                    >
                      {pageNumber}
                    </button>
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="icon-sm"
                    disabled={safePage === totalPages}
                    aria-label="Halaman berikutnya"
                    onClick={() => goToPage(safePage + 1)}
                  >
                    <ChevronRight className="size-4" />
                  </Button>
                </nav>
              ) : null}
            </div>
          ) : null}
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
